# Deploy to your VPS from GitHub

```
you push to main ──▶ GitHub runs the tests ──▶ GitHub logs in to your VPS with the SSH key you gave it
                                                ──▶ uploads the code + your settings ──▶ the bot restarts
```

- The VPS never needs a key to GitHub. GitHub holds the VPS key and sends the code to the server.
- You never copy files to the server by hand. Every push to `main` deploys by itself.
- If the new version doesn't stay up, the previous version starts again automatically.

The workflow is `.github/workflows/deploy.yml`, and the part that runs on the server is `deploy/vps_deploy.sh`.

The server needs Ubuntu 22.04+ or Debian 12+ (Python 3.10 or newer). Python is installed automatically if it's missing.

---

## One-time setup (about 10 minutes)

### Step 1: make a key for GitHub (on your VPS)

Log in to your VPS the way you usually do. Use **root**, or a user with passwordless sudo (see *If something goes wrong*). Then paste:

```bash
ssh-keygen -t ed25519 -N "" -C github-deploy -f ~/.ssh/github_deploy
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
cat ~/.ssh/github_deploy
```

The last command prints the **private key**. Copy all of it, from `-----BEGIN OPENSSH PRIVATE KEY-----` to `-----END OPENSSH PRIVATE KEY-----`, including those two lines. If copying loses the line breaks, picks up the prompt around the key, or turns `-----` into long dashes (phones do this), that's fine: the workflow repairs it.

After you save it in GitHub (step 2), delete it from the server. The server only needs the public half, which is already in `authorized_keys`:

```bash
rm ~/.ssh/github_deploy
```

### Step 2: add the secrets on GitHub

Go to the repository on GitHub, then **Settings → Secrets and variables → Actions → New repository secret**. Add each row as its own secret:

| Name | What to put | Needed? |
|---|---|---|
| `VPS_HOST` | the server's IP address, e.g. `203.0.113.10` | **yes** |
| `VPS_USER` | the user you logged in as in step 1, e.g. `root` | **yes** |
| `VPS_SSH_KEY` | the private key you copied in step 1 | **yes** |
| `BOT_TOKEN` | the token from @BotFather | **yes** |
| `BOT_USERNAME` | the bot's username **without** `@` | recommended |
| `DB_PATH` | where the database file lives, e.g. `/data/karagah.db` | optional (default: `~/karagah/data/karagah.db`) |
| `ADMIN_IDS` | your numeric Telegram ID (several: `111,222`) | optional |
| `VPS_PORT` | the SSH port, only if it isn't 22 | optional |
| `BOT_EXTRA_ENV` | any other setting, one per line, e.g. `NIGHT_SECONDS=90` | optional |
| `VPS_KNOWN_HOSTS` | pins the server's identity: the output of `ssh-keyscan YOUR_SERVER_IP` run on **your own computer** | optional |

Two optional **variables** go on the *Variables* tab, not *Secrets*. You rarely need them:
- `VPS_APP_DIR`: where the bot lives on the server (default `~/karagah`).
- `VPS_SERVICE`: the service name (default `karagah`).

### Step 3: deploy

Go to the **Actions** tab, choose **deploy**, click **Run workflow**, and pick `main`.

The first run takes 1–2 minutes. A green check means the bot is running. After this, every push to `main` deploys by itself.

---

## What ends up on the VPS

```
~/karagah/
├── app/        the code of the deployed commit (replaced on every deploy)
├── app.old/    the previous version, kept for automatic rollback
├── venv/       Python packages (kept between deploys)
└── bot.env     the settings, written from the GitHub secrets (only your user can read it)
DB_PATH         the database, e.g. /data/karagah.db (a deploy never touches it)
```

The bot runs as the systemd service `karagah`. It starts again by itself after a crash or a server reboot.

## Everyday commands on the VPS

| What | Command |
|---|---|
| Is it running? | `systemctl status karagah` |
| Live log | `journalctl -u karagah -f` |
| Restart | `systemctl restart karagah` |
| Stop | `systemctl stop karagah` |

Add `sudo` in front if you aren't root. To change a setting, edit the secret on GitHub and run the workflow again.

## If something goes wrong

Open the failed run on the **Actions** tab. The red message tells you what to fix:

| Message | Fix |
|---|---|
| `The VPS_HOST secret is not set yet` | Do step 2. |
| `These secrets are missing: …` | Add the secrets it names. |
| `VPS_SSH_KEY: this is the PUBLIC key` | You pasted the `.pub` file. Paste the output of `cat ~/.ssh/github_deploy` (no `.pub`). |
| `VPS_SSH_KEY: … fingerprint / picture` | You copied what `ssh-keygen` printed while making the key (`SHA256:…` and the box of symbols). Run `cat ~/.ssh/github_deploy` and copy **that** output. |
| `VPS_SSH_KEY: … looks like a password` | GitHub logs in with the key file, not with the VPS password. Paste the output of `cat ~/.ssh/github_deploy`. |
| `VPS_SSH_KEY: no -----BEGIN … line found` | Whatever was pasted isn't a key. Paste the output of `cat ~/.ssh/github_deploy`. |
| `VPS_SSH_KEY: the key is cut off` / `is damaged` | Part of the key is missing. Copy it again, from `-----BEGIN` to `-----END … KEY-----`. |
| `VPS_SSH_KEY: … protected by a passphrase` | GitHub can't type a password. Make the key exactly as in step 1 (`-N ""` means no passphrase). |
| `VPS_SSH_KEY: this is a PuTTY (.ppk) key` | Make a new key as in step 1, or export it from PuTTYgen with *Conversions → Export OpenSSH key*. |
| `Could not reach SSH on the VPS …` | Check `VPS_HOST` and `VPS_PORT`. Your server's firewall (ufw, fail2ban, or the provider's control panel) must allow SSH from anywhere, because GitHub connects from changing addresses. The workflow uses a single SSH connection, so `ufw limit` is fine. |
| `The VPS refused the key` | `VPS_USER` is wrong, or the `github-deploy` line isn't in that user's `~/.ssh/authorized_keys`. Repeat step 1 as that user. |
| `User '…' needs sudo without a password` | Use `root` as `VPS_USER`, or on the server run `echo "$USER ALL=(ALL) NOPASSWD:ALL" \| sudo tee /etc/sudoers.d/github-deploy`. This gives that user full sudo. |
| `User '…' cannot write to /data` | On the server run the `sudo chown …` command the message shows. |
| `DB_PATH … is a folder` / `must end with a file name` | Use a file path, e.g. `/data/karagah.db`. |
| `The new version did not stay up …` | The previous version is running again. The bot's log is in the same job output (expand *Bot log since start*). An invalid token means the `BOT_TOKEN` secret is wrong. |
| warning `another copy of this bot is running` | Stop the bot anywhere else (your PC, an older install). Only one copy may run per token. |

## Security

- If the repository is public, anyone can read its Actions logs. Secrets are always shown as `***`, and after a successful deploy the log shows nothing about your server beyond that the bot is running. Only a failed start prints the bot's own log, because it's needed to see what went wrong.

- The key lets GitHub log in to your server. It is stored only in GitHub secrets, which are encrypted and hidden in logs.
- Anyone who can push to this repository could change the workflow and use the key, so give write access only to people you trust.
- To revoke GitHub's access, delete the line ending in `github-deploy` from `~/.ssh/authorized_keys` on the VPS.
