"""Read-only credential-pattern scan of tracked text and reachable Git history.

Never prints matched values or reads the untracked live .env/database.
This is a narrow signature scan, not proof of absence of all secrets.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "telegram_token": re.compile(rb"(?<![A-Za-z0-9])[0-9]{6,12}:[A-Za-z0-9_-]{30,60}(?![A-Za-z0-9_-])"),
    "private_key_header": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "openai_style_key": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b"),
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def scan(data, path, scope, oid=None):
    found = []
    for label, pattern in PATTERNS.items():
        for match in pattern.finditer(data):
            found.append({"kind": label, "path": path, "scope": scope, "object": oid,
                          "line": data[:match.start()].count(b"\n") + 1,
                          "fingerprint": hashlib.sha256(match.group()).hexdigest()[:12]})
    return found


def main():
    tracked = git("ls-files", "-z").decode("utf-8").split("\0")
    tracked = [p for p in tracked if p]
    findings, sensitive_paths = [], []
    texts = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".env"}
    for path in tracked:
        p = Path(path)
        if p.name == ".env" or p.suffix in {".db", ".sqlite", ".sqlite3", ".pem", ".key"}:
            sensitive_paths.append(path)
        if p.suffix in texts or p.name in {".env", ".env.example", ".gitignore"}:
            findings += scan(git("show", f"HEAD:{path}"), path, "HEAD")
    seen, inspected = set(), 0
    for line in git("rev-list", "--objects", "--all").decode("utf-8").splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        oid, path = parts
        p = Path(path)
        if oid in seen or not (p.suffix in texts or p.name in {".env", ".env.example"}):
            continue
        seen.add(oid)
        if git("cat-file", "-t", oid).strip() != b"blob":
            continue
        size = int(git("cat-file", "-s", oid))
        if size > 2_000_000:
            continue
        inspected += 1
        findings += scan(git("cat-file", "blob", oid), path, "reachable_history", oid)
    report = {"head": git("rev-parse", "HEAD").decode().strip(),
              "tracked_paths": len(tracked), "history_text_blobs_scanned": inspected,
              "tracked_sensitive_file_paths": sensitive_paths, "matches": findings,
              "limits": "Signature scan only; excludes untracked .env, live DB, remote-only history, binaries, and blobs above 2 MB."}
    destination = ROOT / "qa_results" / "repository_leak_scan.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "matches"}, ensure_ascii=True))
    print("Pattern matches:", len(findings), "(values redacted in report)")


if __name__ == "__main__":
    main()
