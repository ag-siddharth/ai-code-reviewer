"""
Basic tests for the code reviewer.
Run with: python -m pytest tests/
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.utils import load_config, collect_files, chunk_file


def test_load_config_defaults():
    """Should return defaults when no config file exists."""
    config = load_config("nonexistent.yaml")
    assert "model" in config
    assert "extensions" in config
    assert "py" in config["extensions"]


def test_load_config_from_file(tmp_path):
    cfg_file = tmp_path / "test_config.yaml"
    cfg_file.write_text("model: claude-haiku-4-5\nmax_files: 10\n")

    config = load_config(str(cfg_file))
    assert config["model"] == "claude-haiku-4-5"
    assert config["max_files"] == 10
    # defaults should still be there
    assert "extensions" in config


def test_collect_files(tmp_path):
    # create some test files
    (tmp_path / "a.py").write_text("print('hello')")
    (tmp_path / "b.ts").write_text("console.log('hello')")
    (tmp_path / "c.txt").write_text("not code")

    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "d.py").write_text("# nested")

    # should only pick up .py files
    files = collect_files(tmp_path, ["py"])
    names = [f.name for f in files]
    assert "a.py" in names
    assert "d.py" in names
    assert "b.ts" not in names
    assert "c.txt" not in names


def test_collect_files_ignores_dirs(tmp_path):
    (tmp_path / "good.py").write_text("x = 1")
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "bad.py").write_text("x = 2")

    files = collect_files(tmp_path, ["py"], ignore_dirs=["venv"])
    names = [f.name for f in files]
    assert "good.py" in names
    assert "bad.py" not in names


def test_chunk_file_small():
    code = "line1\nline2\nline3"
    chunks = chunk_file(code, max_lines=500)
    assert len(chunks) == 1
    assert chunks[0]["start_line"] == 0


def test_chunk_file_large():
    # 100 lines should get split into chunks of 20
    code = "\n".join([f"line_{i}" for i in range(100)])
    chunks = chunk_file(code, max_lines=20)
    assert len(chunks) > 1
    # make sure we cover all lines
    total_lines = sum(
        c["end_line"] - c["start_line"] for c in chunks
    )
    assert total_lines == 100
