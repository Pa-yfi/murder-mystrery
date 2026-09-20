import importlib


def test_run_module_imports():
    run = importlib.import_module("run")
    assert hasattr(run, "main")
