"""Stage 3: voiceover with word-level timings, via Microsoft Edge's free neural TTS (edge-tts)."""

from __future__ import annotations

import asyncio
import os
import time
from difflib import SequenceMatcher
from pathlib import Path

import edge_tts
from edge_tts.exceptions import NoAudioReceived

VOICE = os.getenv("TTS_VOICE", "en-US-AndrewNeural")
RATE = os.getenv("TTS_RATE", "+8%")  # a touch faster than default suits short-form pacing
TICKS = 10_000_000  # edge-tts reports offsets in 100-nanosecond ticks


async def _stream(text: str, mp3: Path, voice: str) -> list[dict]:
    boundaries = []
    communicate = edge_tts.Communicate(text, voice, rate=RATE, boundary="WordBoundary")
    with open(mp3, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS
                boundaries.append({"word": chunk["text"], "start": start,
                                   "end": start + chunk["duration"] / TICKS})
    return boundaries


def synthesize(text: str, out_dir: Path, voice: str = VOICE) -> list[dict]:
    """Write voice.mp3 and return [{word, start, end}] (seconds) for every word of `text`."""
    expected = len(_norm(text))
    for attempt in range(3):
        try:
            # The free service sometimes drops a request, stalls mid-stream without tripping
            # edge-tts's own timeout, or ends the stream early without an error. Cap the whole
            # request, and treat audio that covers too little of the script as a failure.
            boundaries = asyncio.run(asyncio.wait_for(
                _stream(text, out_dir / "voice.mp3", voice), timeout=180))
            spoken = sum(len(_norm(b["word"])) for b in boundaries)
            if spoken < 0.9 * expected:
                raise RuntimeError(f"edge-tts spoke only {spoken} of {expected} letters "
                                   f"({voice}); the audio was cut short")
            break
        except (NoAudioReceived, TimeoutError, RuntimeError):
            if attempt == 2:
                raise
            time.sleep(3)
    return align(script_words(text), boundaries)


def _norm(s: str) -> str:
    # Letters and digits in any script (é, Devanagari, Arabic), so non-English words aren't
    # mistaken for punctuation. Combining marks (Hindi vowel signs, Arabic diacritics) are
    # dropped on both sides, which is fine for matching.
    return "".join(c for c in s.casefold() if c.isalnum())


def script_words(text: str) -> list[str]:
    """Whitespace-split words, with punctuation-only tokens ("—") glued onto the previous word."""
    words: list[str] = []
    for t in text.split():
        if not _norm(t) and words:
            words[-1] += f" {t}"
        else:
            words.append(t)
    return words


def align(words: list[str], boundaries: list[dict]) -> list[dict]:
    """Put TTS timings onto the script's own words.

    The TTS drops punctuation and dashes and may split or merge words, but captions need the
    script's punctuation (it drives caption grouping) and section boundaries need the script's
    word count. So match the two letter streams and give each script word the time span of
    the TTS words its letters landed in.
    """
    s_owner = [i for i, w in enumerate(words) for _ in _norm(w)]
    b_owner = [j for j, b in enumerate(boundaries) for _ in _norm(b["word"])]
    s_str = "".join(_norm(w) for w in words)
    b_str = "".join(_norm(b["word"]) for b in boundaries)

    # For each TTS word, count how many matched letters belong to each script word.
    shares: dict[int, dict[int, int]] = {}
    matcher = SequenceMatcher(None, s_str, b_str, autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            per_word = shares.setdefault(b_owner[block.b + k], {})
            i = s_owner[block.a + k]
            per_word[i] = per_word.get(i, 0) + 1

    # One TTS word can cover several script words (it reports "In 1518" as one), so split its
    # time between them in proportion to their letters.
    spans: list[list[float] | None] = [None] * len(words)
    for j, per_word in shares.items():
        b = boundaries[j]
        total = sum(per_word.values())
        t = b["start"]
        for i in sorted(per_word):
            end = t + (b["end"] - b["start"]) * per_word[i] / total
            if spans[i] is None:
                spans[i] = [t, end]
            else:
                spans[i][0], spans[i][1] = min(spans[i][0], t), max(spans[i][1], end)
            t = end

    # Words the TTS spoke differently (e.g. digits) get times interpolated from their neighbours.
    out = []
    for i, w in enumerate(words):
        if spans[i] is None:
            prev_end = out[-1]["end"] if out else 0.0
            nxt = next((s[0] for s in spans[i + 1:] if s), prev_end + 0.3)
            spans[i] = [prev_end, max(prev_end, nxt)]
        start = max(spans[i][0], out[-1]["start"] if out else 0.0)
        out.append({"word": w, "start": start, "end": max(start, spans[i][1])})
    return out


def section_times(sections: list[str], words: list[dict]) -> list[tuple[float, float]]:
    """(start, end) of each script section, found by counting words in order."""
    spans = []
    i = 0
    for section in sections:
        n = len(script_words(section))
        chunk = words[i:i + n] or words[-1:]
        spans.append((chunk[0]["start"], chunk[-1]["end"]))
        i += n
    # Make spans contiguous so every frame has a visual: each section runs until the next starts.
    total = words[-1]["end"] + 0.6
    return [(0.0 if k == 0 else spans[k][0],
             spans[k + 1][0] if k + 1 < len(spans) else total)
            for k in range(len(spans))]
