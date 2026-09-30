#!/usr/bin/env bash
# Runs ON THE VPS. .github/workflows/deploy.yml uploads a folder over SSH and starts this script with it:
#   $1/app      the code of the commit being deployed
#   $1/bot.env  the bot settings, built from the GitHub secrets
# What it keeps on the server:
#   $APP_DIR/app       the code (replaced on every deploy; the previous one stays as app.old for rollback)
#   $APP_DIR/venv      Python packages (kept, only updated)
#   $APP_DIR/bot.env   the settings (rewritten on every deploy)
#   DB_PATH            the SQLite database (never touched; default $APP_DIR/data/karagah.db)
# The bot runs as the systemd service $SERVICE, so it restarts by itself after a crash or a reboot.
set -euo pipefail

UPLOAD=${1:?usage: vps_deploy.sh UPLOAD_DIR}
APP_DIR=${APP_DIR:-$HOME/karagah}
APP_DIR=${APP_DIR/#\~/$HOME}
APP_DIR=${APP_DIR%/}
SERVICE=${SERVICE:-karagah}
RUN_AS=$(id -un)
trap 'rm -rf "$UPLOAD"' EXIT

say() { printf '▶ %s\n' "$*"; }
die() { printf '::error::%s\n' "$*"; exit 1; }
as_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo -n "$@"; fi; }

case "$APP_DIR" in
  /?*) ;;
  *) die "VPS_APP_DIR must be a full folder path such as /home/$RUN_AS/karagah (got '$APP_DIR')." ;;
esac
case "$APP_DIR" in *[[:space:]]*) die "VPS_APP_DIR must not contain spaces (got '$APP_DIR')." ;; esac
[[ $SERVICE =~ ^[A-Za-z0-9_-]+$ ]] || die "VPS_SERVICE may only use letters, digits, - and _ (got '$SERVICE')."
as_root true 2>/dev/null \
  || die "User '$RUN_AS' needs sudo without a password to install the service. Use root as VPS_USER, or see DEPLOY.md."

# ── 1. Python 3.10+ and a virtualenv ─────────────────────────────────────────
install_pkgs() {
  command -v apt-get >/dev/null || die "Please install $* on the server (this script only knows apt-get)."
  say "Installing $*"
  as_root env DEBIAN_FRONTEND=noninteractive apt-get update -qq
  as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" >/dev/null
}
command -v python3 >/dev/null || install_pkgs python3 python3-venv
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
  || die "The server has $(python3 -V 2>&1); the bot needs Python 3.10 or newer (Ubuntu 22.04+ or Debian 12+)."

mkdir -p "$APP_DIR"
VENV=$APP_DIR/venv
if ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then       # missing, or broken by a Python upgrade
  say "Creating the Python environment"
  rm -rf "$VENV"
  if ! python3 -m venv "$VENV" >/dev/null 2>&1; then
    rm -rf "$VENV"
    install_pkgs python3-venv
    python3 -m venv "$VENV"
  fi
fi
say "Installing requirements"
echo "::group::pip install"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check -r "$UPLOAD/app/requirements.txt"
echo "::endgroup::"

# ── 2. Settings and the database location ───────────────────────────────────
ENV_NEW=$UPLOAD/bot.env
grep -q '^BOT_TOKEN=.' "$ENV_NEW" || die "The BOT_TOKEN secret is empty."
db=$(sed -n 's/^DB_PATH=//p' "$ENV_NEW" | tail -n 1)
db=${db/#\~/$HOME}
case "$db" in
  "") db=$APP_DIR/data/karagah.db ;;
  /*) ;;
  *) db=$APP_DIR/data/$db ;;                 # a bare name would sit in the code folder and vanish on redeploy
esac
case "$db" in
  */) die "DB_PATH must end with a file name, for example ${db}karagah.db" ;;
  "$APP_DIR"/app/*|"$APP_DIR"/app.*/*)
    die "DB_PATH ($db) is inside the code folder, which is replaced on every deploy. Use $APP_DIR/data/karagah.db" ;;
esac
if [ -d "$db" ]; then die "DB_PATH ($db) is a folder; it must be a file path such as $db/karagah.db"; fi
db_dir=$(dirname "$db")
if [ ! -d "$db_dir" ]; then
  say "Creating the database folder $db_dir"
  if ! mkdir -p "$db_dir" 2>/dev/null; then
    as_root mkdir -p "$db_dir" && as_root chown "$RUN_AS" "$db_dir" || die "Could not create $db_dir."
  fi
fi
[ -w "$db_dir" ] || die "User '$RUN_AS' cannot write to $db_dir. On the server run: sudo chown $RUN_AS $db_dir"
{ grep -v '^DB_PATH=' "$ENV_NEW" || true; printf 'DB_PATH=%s\n' "$db"; } > "$APP_DIR/bot.env.new"
chmod 600 "$APP_DIR/bot.env.new"
mv -f "$APP_DIR/bot.env.new" "$APP_DIR/bot.env"

# ── 3. Swap in the new code and (re)start the service ────────────────────────
say "Stopping the bot"
as_root systemctl stop "$SERVICE" 2>/dev/null || true
rm -rf "$APP_DIR/app.old" "$APP_DIR/app.new"
mv "$UPLOAD/app" "$APP_DIR/app.new"
if [ -d "$APP_DIR/app" ]; then mv "$APP_DIR/app" "$APP_DIR/app.old"; fi
mv "$APP_DIR/app.new" "$APP_DIR/app"

as_root tee "/etc/systemd/system/$SERVICE.service" >/dev/null <<EOF
[Unit]
Description=Karagah Telegram bot ($SERVICE)
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_AS
WorkingDirectory=$APP_DIR/app
EnvironmentFile=$APP_DIR/bot.env
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
say "Starting the bot"
started=$(date +%s)
as_root systemctl daemon-reload
as_root systemctl enable --quiet "$SERVICE"
as_root systemctl restart "$SERVICE"

# ── 4. Make sure it stays up; otherwise put the previous version back ────────
say "Waiting 15 seconds to be sure the bot stays up"
sleep 15
logs=$(as_root journalctl -u "$SERVICE" --since "@$started" --no-pager -o cat 2>/dev/null | tail -n 40 || true)
if printf '%s' "$logs" | grep -q 'Conflict'; then
  echo "::warning::Telegram says another copy of this bot is running somewhere else (your PC or an older install). Stop the other copy."
fi
if [ "$(as_root systemctl is-active "$SERVICE")" = active ] \
   && [ "$(as_root systemctl show -p NRestarts --value "$SERVICE")" = 0 ]; then
  rm -rf "$APP_DIR/app.bad"
  say "✅ The bot is running: service '$SERVICE', code in $APP_DIR/app, database $db"
  echo "::notice::Deployed: the bot is running as service '$SERVICE'."
  exit 0
fi

# Only a failed start prints the bot's log (Actions logs of a public repository are public).
echo "::group::Bot log since start"
printf '%s\n' "$logs"
echo "::endgroup::"

hint="The log is above; if it says the token is invalid, fix the BOT_TOKEN secret."
if [ -d "$APP_DIR/app.old" ]; then
  say "The new version did not stay up; putting the previous version back"
  as_root systemctl stop "$SERVICE" || true
  rm -rf "$APP_DIR/app.bad"
  mv "$APP_DIR/app" "$APP_DIR/app.bad"
  mv "$APP_DIR/app.old" "$APP_DIR/app"
  as_root systemctl restart "$SERVICE"
  die "The new version did not stay up, so the previous version was started again. $hint"
fi
die "The bot did not stay up. $hint"
