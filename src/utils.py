"""
Shared utilities.
"""

import os
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()
logger = logging.getLogger(__name__)

_client = None


def get_client():
    """Get or create the Anthropic client."""
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Add it to .env or export it."
            )
        _client = Anthropic(api_key=api_key)
    return _client


def load_config(config_path="config.yaml"):
    """Load config from YAML file. Returns defaults if file not found."""
    defaults = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 2000,
        "max_files": 50,
        "extensions": ["py", "ts"],
        "ignore_dirs": ["node_modules", "__pycache__", ".git", "venv", "dist", "build"],
        "review_focus": ["missing_error_handling", "type_hints", "docstrings", "security", "naming"],
    }

    config_path = Path(config_path)
    if config_path.exists():
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        defaults.update(user_config)

    return defaults


def collect_files(directory, extensions, ignore_dirs=None):
    """
    Recursively collect files with given extensions from a directory.
    Skips directories in ignore_dirs list.
    """
    if ignore_dirs is None:
        ignore_dirs = []

    directory = Path(directory)
    files = []

    for ext in extensions:
        for f in directory.rglob(f"*.{ext}"):
            # check if any parent dir should be ignored
            parts = f.relative_to(directory).parts
            if any(d in ignore_dirs for d in parts[:-1]):
                continue
            files.append(f)

    files.sort()
    return files


def chunk_file(code, max_lines=500):
    """
    Split a file into chunks for processing.
    Tries to break at function boundaries if possible.
    """
    lines = code.split("\n")

    if len(lines) <= max_lines:
        return [{"code": code, "start_line": 0, "end_line": len(lines)}]

    chunks = []
    start = 0

    while start < len(lines):
        end = min(start + max_lines, len(lines))

        # try to find a good break point (empty line or function def)
        if end < len(lines):
            for i in range(end, max(start + max_lines // 2, start), -1):
                line = lines[i].strip()
                if line == "" or line.startswith("def ") or line.startswith("class ") or line.startswith("function "):
                    end = i
                    break

        chunk_code = "\n".join(lines[start:end])
        chunks.append({
            "code": chunk_code,
            "start_line": start,
            "end_line": end,
        })
        start = end

    return chunks


def estimate_cost(file_paths):
    """
    Rough cost estimate for reviewing a set of files.
    Based on average token counts, not exact.
    """
    total_chars = 0
    for fp in file_paths:
        try:
            total_chars += Path(fp).stat().st_size
        except OSError:
            pass

    # rough estimate: ~4 chars per token, input + output
    estimated_tokens = total_chars / 4
    # claude sonnet pricing (approx)
    cost = (estimated_tokens * 3 / 1_000_000) + (estimated_tokens * 0.5 * 15 / 1_000_000)

    return round(cost, 4)
