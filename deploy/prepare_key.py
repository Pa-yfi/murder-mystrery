"""Turns the VPS_SSH_KEY secret into a key file ssh can use, or says exactly what is wrong with it.

Used by .github/workflows/deploy.yml:  python3 deploy/prepare_key.py OUT_FILE   (the key comes from $VPS_SSH_KEY)

Repairs the usual copy/paste damage without asking: line breaks turned into spaces or lost, Windows line
endings, indentation, a shell prompt or other text around the key, only the middle of the key copied.
Names what it cannot repair: the public key instead of the private one, the fingerprint or randomart picture,
a password, a PuTTY key, a key cut off before its END line, a key with a passphrase.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

HELP = "On the VPS run `cat ~/.ssh/github_deploy` (step 1 in DEPLOY.md) and paste everything it prints."
PUBLIC = re.compile(r"(ssh-(ed25519|rsa|dss)|ecdsa-sha2-\S+|sk-\S+)\s+AAAA")
OPENSSH_BODY = "b3BlbnNzaC1rZXktdjE"          # base64 of "openssh-key-v1", how every OpenSSH private key starts


class BadKey(Exception):
    pass


def normalize(raw: str) -> str:
    """The key in the exact layout ssh expects, or BadKey with a message for the user."""
    text = raw.replace("\r", "").strip()
    if not text:
        raise BadKey("the secret is empty. " + HELP)
    if "PuTTY-User-Key-File" in text:
        raise BadKey("this is a PuTTY (.ppk) key. In PuTTYgen use Conversions → Export OpenSSH key "
                     "and paste that file instead, or make a new key: " + HELP)
    begin = re.search(r"-----BEGIN ([A-Z0-9 ]+)-----", text)
    if not begin:
        if PUBLIC.search(text):
            raise BadKey("this is the PUBLIC key (the .pub file, starting with ssh-…). "
                         "GitHub needs the PRIVATE key, the one without .pub. " + HELP)
        if "".join(text.split()).startswith(OPENSSH_BODY):     # only the middle was copied
            text = f"-----BEGIN OPENSSH PRIVATE KEY-----\n{text}\n-----END OPENSSH PRIVATE KEY-----"
            begin = re.search(r"-----BEGIN ([A-Z0-9 ]+)-----", text)
        elif "SHA256:" in text or "randomart" in text or re.search(r"\+-+\[", text):
            raise BadKey("this is the key's fingerprint / picture that ssh-keygen shows while making the key, "
                         "not the key itself. " + HELP)
        elif "\n" not in text and len(text) < 200:
            raise BadKey("this looks like a password or a short code, not a key. GitHub logs in with the "
                         "private key file, not with the VPS password. " + HELP)
        else:
            raise BadKey("no -----BEGIN OPENSSH PRIVATE KEY----- line found. " + HELP)
    kind = begin.group(1)
    end = text.find(f"-----END {kind}-----", begin.end())
    if end < 0:
        raise BadKey(f"the key is cut off: its last line (-----END {kind}-----) is missing. "
                     "Copy it again, all the way to the end.")
    body = text[begin.end():end]
    if "ENCRYPTED" in kind or "ENCRYPTED" in body:
        raise BadKey("this key is protected by a passphrase, which GitHub cannot type. " + HELP)
    b64 = "".join(body.split())
    if not re.fullmatch(r"[A-Za-z0-9+/]+=*", b64):
        raise BadKey("the key contains characters that do not belong to a key. Copy it again. " + HELP)
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return f"-----BEGIN {kind}-----\n" + "\n".join(lines) + f"\n-----END {kind}-----\n"


def check(path: str) -> str:
    """ssh-keygen must be able to read the key without a passphrase; returns its fingerprint line."""
    r = subprocess.run(["ssh-keygen", "-y", "-P", "", "-f", path], capture_output=True, text=True)
    if r.returncode:
        if "passphrase" in r.stderr.lower():
            raise BadKey("this key is protected by a passphrase, which GitHub cannot type. " + HELP)
        raise BadKey("the key is damaged: part of it is missing or changed. Copy it again. " + HELP)
    fp = subprocess.run(["ssh-keygen", "-l", "-f", path], capture_output=True, text=True)
    return fp.stdout.strip()


def main(out: str) -> int:
    try:
        key = normalize(os.environ.get("VPS_SSH_KEY", ""))
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key)
        fp = check(out)
    except BadKey as e:
        print(f"::error::VPS_SSH_KEY: {e}")
        return 1
    print(f"Key OK: {fp}")
    print("Its public half must be in ~/.ssh/authorized_keys of VPS_USER on the VPS.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
