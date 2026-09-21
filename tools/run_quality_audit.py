"""Offline audit of a stable source snapshot. Never starts the Telegram bot.

Run: .venv/Scripts/python.exe tools/run_quality_audit.py
Evidence is stored under qa_results/<timestamp>; nonzero means a failing gate.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def capture():
    paths = [*ROOT.joinpath("karagah").rglob("*.py"), *ROOT.joinpath("tests").rglob("*.py"),
             ROOT / "run.py", ROOT / "pytest.ini", ROOT / "requirements.txt"]
    return {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in sorted(paths)}


def main():
    for _ in range(5):
        files = capture()
        time.sleep(0.25)
        if files == capture():
            break
    else:
        raise SystemExit("Source is changing; rerun when editing is finished")
    out = ROOT / "qa_results" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    packages = {}
    for name in ("pytest", "python-telegram-bot", "Pillow", "APScheduler"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "NOT INSTALLED"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    summary = {"revision": revision, "python": sys.version, "packages": packages,
               "sha256": manifest, "scope": "offline; mocked Telegram; no real credentials/database", "suites": {}}
    for name, data in files.items():
        p = out / "source_snapshot" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    with tempfile.TemporaryDirectory(prefix="karagah-audit-") as directory:
        work = Path(directory)
        for name, data in files.items():
            p = work / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        (work / ".env").write_text("BOT_TOKEN=123:offline\nADMIN_IDS=\nLANG_UI=fa\n", encoding="utf-8")
        (work / "conftest.py").write_text('''import socket
import pytest
@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    original_connect = socket.socket.connect
    def local_only(sock, address):
        # Windows asyncio builds its internal wake-up socket over loopback.
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(sock, address)
        raise AssertionError("Offline audit attempted external network access")
    def denied(*args, **kwargs):
        raise AssertionError("Offline audit attempted network access")
    monkeypatch.setattr(socket.socket, "connect", local_only)
    monkeypatch.setattr(socket, "create_connection", denied)
''', encoding="utf-8")
        env = os.environ.copy()
        env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", BOT_TOKEN="123:offline",
                   ADMIN_IDS="", LANG_UI="fa", DB_PATH=str(work / "audit.sqlite3"))
        for key in ("PYTHONPATH", "PYTEST_ADDOPTS", "PYTHON_DOTENV_DISABLED"):
            env.pop(key, None)
        for name, selection in (("existing", ["tests", "--ignore=tests/quality"]),
                                ("quality", ["tests/quality"])):
            xml = out / (name + ".xml")
            cmd = [sys.executable, "-B", "-m", "pytest", *selection, "-q", "--tb=short",
                   "-p", "no:cacheprovider", "--junitxml=" + str(xml)]
            with (out / (name + ".txt")).open("w", encoding="utf-8") as log:
                result = subprocess.run(cmd, cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
            counts = {"exit_code": result.returncode, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "failures": []}
            if xml.exists():
                for case in ET.parse(xml).iter("testcase"):
                    failure, error = case.find("failure"), case.find("error")
                    if failure is not None or error is not None:
                        node = failure if failure is not None else error
                        counts["failed" if failure is not None else "errors"] += 1
                        counts["failures"].append({"test": case.attrib.get("name"), "class": case.attrib.get("classname"),
                                                   "message": node.attrib.get("message", "")})
                    elif case.find("skipped") is not None:
                        counts["skipped"] += 1
                    else:
                        counts["passed"] += 1
            summary["suites"][name] = counts
            print(name, {k: v for k, v in counts.items() if k != "failures"}, flush=True)
    summary["source_changed_during_run"] = [name for name, sha in manifest.items()
        if not (ROOT / name).exists() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha]
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Evidence:", out)
    print("Changed during run:", summary["source_changed_during_run"])
    return int(any(v["exit_code"] for v in summary["suites"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
