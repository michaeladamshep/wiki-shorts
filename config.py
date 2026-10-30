"""Settings, paths and small shared helpers."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

RUNS_DIR = ROOT / "runs"
MUSIC_DIR = ROOT / "music"
PROMPTS_DIR = ROOT / "prompts"
SECRETS_DIR = ROOT / "secrets"
HISTORY_FILE = ROOT / "history.json"

# Wikimedia asks every API client to send a descriptive User-Agent with contact info.
USER_AGENT = os.getenv("WIKI_USER_AGENT", "wiki-shorts/0.1 (https://headgonebynoise.com)")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")

WIDTH, HEIGHT, FPS = 1080, 1920, 30
MIN_WORDS, MAX_WORDS = 130, 165  # ~45-58s of narration
SHOT_SECONDS = 3.2  # target length of each visual shot


def env(name: str, required: bool = True) -> str:
    value = os.getenv(name, "").strip()
    if required and not value:
        raise SystemExit(f"Missing {name}. Add it to {ROOT / '.env'} (see .env.example).")
    return value


def ffmpeg_bin(tool: str = "ffmpeg") -> str:
    """Prefer Homebrew's ffmpeg-full: the slim `ffmpeg` formula lacks libass (needed for captions)."""
    full = Path("/opt/homebrew/opt/ffmpeg-full/bin") / tool
    if full.exists():
        return str(full)
    found = shutil.which(tool)
    if not found:
        raise SystemExit(f"{tool} not found. Run: brew install ffmpeg-full")
    return found


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
