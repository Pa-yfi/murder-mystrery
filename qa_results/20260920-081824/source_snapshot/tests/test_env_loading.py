"""config باید .env را از ریشه‌ی مخزن بخواند — بدون دست‌زدن به .env واقعی."""
import importlib.util
import os
from pathlib import Path

CONFIG_PY = Path(__file__).resolve().parent.parent / "karagah" / "config.py"


def _load(tmp_path):
    spec = importlib.util.spec_from_file_location("project_config", CONFIG_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_env_path_points_at_repo_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.environ.pop("BOT_TOKEN", None)
    module = _load(tmp_path)
    assert module.env_path == CONFIG_PY.parent.parent / ".env"


def test_env_file_is_loaded(tmp_path, monkeypatch):
    """توکن از فایل .env خوانده می‌شود (روی یک .env موقت، نه فایل واقعی)."""
    fake_root = tmp_path / "repo"
    (fake_root / "karagah").mkdir(parents=True)
    (fake_root / ".env").write_text("BOT_TOKEN=test-token-from-env\n", encoding="utf-8")
    target = fake_root / "karagah" / "config.py"
    target.write_text(CONFIG_PY.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    os.environ.pop("BOT_TOKEN", None)
    spec = importlib.util.spec_from_file_location("tmp_config", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.BOT_TOKEN == "test-token-from-env"
