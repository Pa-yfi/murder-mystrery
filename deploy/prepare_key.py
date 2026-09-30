"""Turns the VPS_SSH_KEY secret into a key file ssh can use, or says exactly what is wrong with it.

Used by .github/workflows/deploy.yml:  python3 deploy/prepare_key.py OUT_FILE   (the key comes from $VPS_SSH_KEY)

Repairs the usual copy/paste damage without asking: line breaks turned into spaces or lost, Windows line
endings, indentation, a shell prompt or other text around the key, only the middle of the key copied.
Names what it cannot repair: the public key instead of the private one, the fingerprint or randomart picture,
a password, a PuTTY key, a key cut off before its END line, a key with a passphrase.
Also undoes look-alike characters (long dashes, non-breaking or invisible spaces) that phones and chat apps
put in while copying; when those break the key anyway, it names them (never the key's content).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

HELP = "On the VPS run `cat ~/.ssh/github_deploy` (step 1 in DEPLOY.md) and paste everything it prints."
PUBLIC = re.compile(r"(ssh-(ed25519|rsa|dss)|ecdsa-sha2-\S+|sk-\S+)\s+AAAA")
OPENSSH_BODY = "b3BlbnNzaC1rZXktdjE"          # base64 of "openssh-key-v1", how every OpenSSH private key starts
# Look-alikes that phones, chat apps and editors swap in while copying: typographic dashes for "-",
# non-breaking/thin spaces for " ", and invisible characters. The key looks right but isn't byte-exact.
DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
SPACES = "\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"
INVISIBLE = "\u200b\u200c\u200d\u2060\ufeff\u00ad"
LOOKALIKES = str.maketrans({**{c: "-" for c in DASHES}, **{c: " " for c in SPACES}, **{c: None for c in INVISIBLE}})
BEGIN = re.compile(r"-+ *BEGIN +([A-Z0-9]+(?: +[A-Z0-9]+)*) *-+")


class BadKey(Exception):
    pass


def normalize(raw: str) -> str:
    """The key in the exact layout ssh expects, or BadKey with a message for the user."""
    text = raw.replace("\r", "").translate(LOOKALIKES).strip()
    if not text:
        raise BadKey("the secret is empty. " + HELP)
    if "PuTTY-User-Key-File" in text:
        raise BadKey("this is a PuTTY (.ppk) key. In PuTTYgen use Conversions → Export OpenSSH key "
                     "and paste that file instead, or make a new key: " + HELP)
    begin = BEGIN.search(text)
    if not begin:
        if PUBLIC.search(text):
            raise BadKey("this is the PUBLIC key (the .pub file, starting with ssh-…). "
                         "GitHub needs the PRIVATE key, the one without .pub. " + HELP)
        if "".join(text.split()).startswith(OPENSSH_BODY):     # only the middle was copied
            text = f"-----BEGIN OPENSSH PRIVATE KEY-----\n{text}\n-----END OPENSSH PRIVATE KEY-----"
            begin = BEGIN.search(text)
        elif "SHA256:" in text or "randomart" in text or re.search(r"\+-+\[", text):
            raise BadKey("this is the key's fingerprint / picture that ssh-keygen shows while making the key, "
                         "not the key itself. " + HELP)
        elif "\n" not in text and len(text) < 200:
            raise BadKey("this looks like a password or a short code, not a key. GitHub logs in with the "
                         "private key file, not with the VPS password. " + HELP)
        elif "BEGIN" in text.upper():
            raise BadKey("the BEGIN line is there but was changed while copying" + _unusual(raw)
                         + ". Paste it again from a plain-text source (a terminal or a plain text editor). " + HELP)
        else:
            lines = len(text.splitlines())
            raise BadKey(f"no -----BEGIN OPENSSH PRIVATE KEY----- line found (the secret has {lines} "
                         f"line{'s' * (lines != 1)}{_unusual(raw)}). " + HELP)
    kind = " ".join(begin.group(1).split())
    end_re = re.compile(r"-+ *END +" + " +".join(kind.split()) + r" *-+")
    end = end_re.search(text, begin.end())
    if not end:
        raise BadKey(f"the key is cut off: its last line (-----END {kind}-----) is missing. "
                     "Copy it again, all the way to the end.")
    body = text[begin.end():end.start()]
    if "ENCRYPTED" in kind or "ENCRYPTED" in body:
        raise BadKey("this key is protected by a passphrase, which GitHub cannot type. " + HELP)
    b64 = "".join(body.split())
    if not re.fullmatch(r"[A-Za-z0-9+/]+=*", b64):
        raise BadKey("the key contains characters that do not belong to a key. Copy it again. " + HELP)
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return f"-----BEGIN {kind}-----\n" + "\n".join(lines) + f"\n-----END {kind}-----\n"


def _unusual(raw: str) -> str:
    """Names (never the values) of characters that don't belong in a key file: safe to show in a public log."""
    import unicodedata
    odd = sorted({c for c in raw if ord(c) > 126 or (ord(c) < 32 and c not in "\n\r\t")})
    if not odd:
        return ""
    names = [unicodedata.name(c, f"U+{ord(c):04X}") for c in odd[:4]]
    return "; it contains unusual characters: " + ", ".join(names)


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
