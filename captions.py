"""Burned-in captions: an .ass file with 1-3 words on screen and the spoken word highlighted."""

from __future__ import annotations

from pathlib import Path

from .config import HEIGHT, WIDTH

MAX_GROUP = 3
BREAK_AFTER = (".", ",", "!", "?", ";", ":", "—", "।", "،", "؟", "؛")

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,7,3,2,80,80,620,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

HIGHLIGHT = r"{\c&H00E6FF&\fscx112\fscy112}"  # yellow (ASS colours are BGR), slightly larger
NORMAL = r"{\c&HFFFFFF&\fscx100\fscy100}"


def ts(seconds: float) -> str:
    cs = max(0, round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def groups(words: list[dict]) -> list[list[dict]]:
    out: list[list[dict]] = []
    current: list[dict] = []
    for w in words:
        current.append(w)
        if len(current) == MAX_GROUP or w["word"].endswith(BREAK_AFTER):
            out.append(current)
            current = []
    if current:
        out.append(current)
    return out


def write_ass(words: list[dict], path: Path, font: str = "Arial Black", size: int = 92) -> None:
    lines = [HEADER.format(width=WIDTH, height=HEIGHT, font=font, size=size)]
    all_groups = groups(words)
    for gi, group in enumerate(all_groups):
        # Hold the group on screen until the next group starts, so captions never flicker off.
        group_end = all_groups[gi + 1][0]["start"] if gi + 1 < len(all_groups) else group[-1]["end"] + 0.4
        for wi, w in enumerate(group):
            start = w["start"]
            end = group[wi + 1]["start"] if wi + 1 < len(group) else group_end
            text = " ".join(
                (HIGHLIGHT if j == wi else NORMAL) + g["word"].upper().replace("{", "").replace("}", "")
                for j, g in enumerate(group)
            )
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Cap,,0,0,0,,{text}\n")
    path.write_text("".join(lines))
