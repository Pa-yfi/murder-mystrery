"""deploy/prepare_key.py: the VPS_SSH_KEY secret survives the usual copy/paste damage,
and every mistake it cannot repair gets its own clear message (not one vague error)."""
import importlib.util
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("prepare_key", ROOT / "deploy" / "prepare_key.py")
pk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pk)

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen (OpenSSH)")


def _keygen(tmp_path, name, *extra, passphrase=""):
    path = tmp_path / name
    subprocess.run(["ssh-keygen", "-q", "-N", passphrase, "-C", "github-deploy", "-f", str(path), *extra],
                   check=True)
    return path.read_text(), (tmp_path / f"{name}.pub").read_text().split()[1]


def _run(tmp_path, monkeypatch, capsys, secret):
    out = tmp_path / "loaded_key"
    monkeypatch.setenv("VPS_SSH_KEY", secret)
    code = pk.main(str(out))
    text = capsys.readouterr().out
    pub = None
    if code == 0:
        pub = subprocess.run(["ssh-keygen", "-y", "-P", "", "-f", str(out)], capture_output=True,
                             text=True, check=True).stdout.split()[1]
        assert oct(out.stat().st_mode & 0o777) == "0o600"
    return code, text, pub


@pytest.mark.parametrize("damage", [
    "as_is",
    "newlines_to_spaces",          # pasted through a chat app / web console
    "no_newlines",
    "crlf_indented_with_prompt",   # Windows line endings, indented, shell prompt around it
])
@pytest.mark.parametrize("kind", ["ed25519", "rsa", "rsa_pem"])
def test_valid_key_is_loaded_even_after_copy_paste_damage(tmp_path, monkeypatch, capsys, kind, damage):
    extra = {"ed25519": ["-t", "ed25519"], "rsa": ["-t", "rsa", "-b", "2048"],
             "rsa_pem": ["-t", "rsa", "-b", "2048", "-m", "PEM"]}[kind]
    key, pub = _keygen(tmp_path, "k", *extra)
    if damage == "newlines_to_spaces":
        key = key.replace("\n", " ")
    elif damage == "no_newlines":
        key = key.replace("\n", "")
    elif damage == "crlf_indented_with_prompt":
        key = ("root@vps:~# cat ~/.ssh/github_deploy\r\n"
               + "".join("   " + ln + "\r\n" for ln in key.splitlines()) + "root@vps:~# ")
    code, text, loaded = _run(tmp_path, monkeypatch, capsys, key)
    assert code == 0, text
    assert loaded == pub
    assert "Key OK" in text


def _fails_with(tmp_path, monkeypatch, capsys, secret, words):
    code, text, _ = _run(tmp_path, monkeypatch, capsys, secret)
    assert code == 1
    assert text.startswith("::error::VPS_SSH_KEY:")
    assert words in text, text


def test_public_key_is_named(tmp_path, monkeypatch, capsys):
    _keygen(tmp_path, "k", "-t", "ed25519")
    pub_line = (tmp_path / "k.pub").read_text()
    _fails_with(tmp_path, monkeypatch, capsys, pub_line, "PUBLIC key")


def test_missing_end_line_is_named(tmp_path, monkeypatch, capsys):
    key, _ = _keygen(tmp_path, "k", "-t", "ed25519")
    _fails_with(tmp_path, monkeypatch, capsys, key.rsplit("-----END", 1)[0], "cut off")


def test_missing_middle_is_named(tmp_path, monkeypatch, capsys):
    key, _ = _keygen(tmp_path, "k", "-t", "rsa", "-b", "2048")
    lines = key.splitlines()
    _fails_with(tmp_path, monkeypatch, capsys, "\n".join(lines[:5] + lines[9:]), "damaged")


def test_passphrase_key_is_named(tmp_path, monkeypatch, capsys):
    key, _ = _keygen(tmp_path, "k", "-t", "ed25519", passphrase="secret-words")
    _fails_with(tmp_path, monkeypatch, capsys, key, "passphrase")


def test_passphrase_pem_key_is_named(tmp_path, monkeypatch, capsys):
    key, _ = _keygen(tmp_path, "k", "-t", "rsa", "-b", "2048", "-m", "PEM", passphrase="secret-words")
    _fails_with(tmp_path, monkeypatch, capsys, key, "passphrase")


def test_putty_key_is_named(tmp_path, monkeypatch, capsys):
    ppk = "PuTTY-User-Key-File-3: ssh-ed25519\nEncryption: none\nComment: vps\nPublic-Lines: 2\nAAAAC3Nz\n"
    _fails_with(tmp_path, monkeypatch, capsys, ppk, "PuTTY")


@pytest.mark.parametrize("secret,words", [("", "empty"), ("   \n ", "empty"),
                                          ("my server password", "no -----BEGIN")])
def test_empty_or_unrelated_text_is_named(tmp_path, monkeypatch, capsys, secret, words):
    _fails_with(tmp_path, monkeypatch, capsys, secret, words)
