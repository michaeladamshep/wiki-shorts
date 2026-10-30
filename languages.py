"""Output languages: voice, captions font, audience and posting accounts for each one.

English is the source language. Every other language is a translation of the English script,
voiced natively and posted to its own set of accounts (see publish/base.py), because posting a
second language on the English accounts shows it to the wrong audience.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import ROOT

FONTS_DIR = ROOT / "fonts"
MAC_FONTS = "/System/Library/Fonts/Supplemental"  # Arial Black lives here on macOS
# Evenings are peak short-form viewing time almost everywhere; override with POST_HOUR.
POST_HOUR = int(os.getenv("POST_HOUR", "19"))


@dataclass(frozen=True)
class Lang:
    code: str
    name: str
    wiki: str  # Wikipedia edition, for the article's local title
    voice: str  # edge-tts voice
    youtube: str  # YouTube defaultLanguage / defaultAudioLanguage code
    tz: str  # where most of the audience lives, for posting times
    style: str  # register and dialect notes for the translator
    max_words: int = 160  # fits ~57s at this voice's measured pace (Tunguska test, 2026-10-29)
    font: str = "Arial Black"
    font_size: int = 92  # non-Latin scripts have no capitals, so they need a bigger size to match
    fonts_dir: str = MAC_FONTS
    skip: tuple[str, ...] = ()  # platforms that don't reach this audience
    labels: dict[str, str] = field(default_factory=dict)  # credit line labels

    @property
    def suffix(self) -> str:
        """Env var suffix for this language's accounts ("" for English, "_ES" for Spanish)."""
        return "" if self.code == "en" else f"_{self.code.upper()}"

    @property
    def tts_voice(self) -> str:
        return os.getenv(f"TTS_VOICE{self.suffix}", self.voice)


LANGUAGES = {
    "en": Lang("en", "English", "en", "en-US-AndrewNeural", "en", "America/New_York", ""),
    "es": Lang(
        "es", "Spanish (Latin America)", "es", "es-MX-JorgeNeural", "es-419", "America/Mexico_City",
        "Neutral Latin American Spanish that works from Mexico to Argentina. Address the viewer "
        "as tú. Avoid Spain-only words and vosotros.", max_words=125,
        labels={"source": "Fuente", "image": "Imagen", "video": "Video de stock"}),
    "pt": Lang(
        "pt", "Portuguese (Brazil)", "pt", "pt-BR-AntonioNeural", "pt", "America/Sao_Paulo",
        "Brazilian Portuguese, informal and lively, addressing the viewer as você. Avoid "
        "European Portuguese vocabulary.", max_words=120,
        labels={"source": "Fonte", "image": "Imagem", "video": "Vídeo de banco"}),
    "hi": Lang(
        "hi", "Hindi", "hi", "hi-IN-MadhurNeural", "hi", "Asia/Kolkata",
        "Everyday spoken Hindi in Devanagari, the way popular Indian YouTube narrators talk. "
        "Not formal or Sanskritised: use common English loanwords where Hindi speakers would "
        "(e.g. 'scientist', 'record'), written in Devanagari.", max_words=115,
        font="Noto Sans Devanagari Black", font_size=110, fonts_dir=str(FONTS_DIR),
        skip=("tiktok",),  # TikTok has been banned in India since 2020
        labels={"source": "स्रोत", "image": "चित्र", "video": "स्टॉक फुटेज"}),
    "id": Lang(
        "id", "Indonesian", "id", "id-ID-ArdiNeural", "id", "Asia/Jakarta",
        "Casual standard Indonesian (bahasa sehari-hari) as used by Indonesian creators: "
        "relaxed but clear, light on slang so it reads well across the country.", max_words=125,
        labels={"source": "Sumber", "image": "Gambar", "video": "Video stok"}),
    "ar": Lang(
        "ar", "Arabic", "ar", "ar-EG-ShakirNeural", "ar", "Africa/Cairo",
        "Simple, lively Modern Standard Arabic that viewers from Morocco to the Gulf all "
        "understand. No diacritics (tashkeel) except where a word would otherwise be misread.",
        max_words=95,
        font="Noto Sans Arabic Blk", font_size=110, fonts_dir=str(FONTS_DIR),
        labels={"source": "المصدر", "image": "صورة", "video": "لقطات أرشيفية"}),
}

TRANSLATIONS = [code for code in LANGUAGES if code != "en"]


def get(code: str) -> Lang:
    try:
        return LANGUAGES[code.strip().lower()]
    except KeyError:
        raise SystemExit(f"Unknown language {code!r}. Use: {', '.join(LANGUAGES)}") from None


def parse(codes: str | None, default: list[str]) -> list[Lang]:
    """`--langs es,pt` → [Lang, Lang]; empty/None → `default`; "none" → []."""
    if codes is None:
        return [get(c) for c in default]
    if codes.strip().lower() in ("", "none"):
        return []
    return [get(c) for c in codes.split(",")]


def default_translations() -> list[str]:
    """Languages `make` translates into: LANGS in .env, else all of them."""
    raw = os.getenv("LANGS")
    return [c.strip() for c in raw.split(",") if c.strip()] if raw else TRANSLATIONS


def next_post_time(lang: Lang) -> datetime:
    """The next POST_HOUR o'clock in the audience's time zone, at least 30 minutes away."""
    now = datetime.now(ZoneInfo(lang.tz))
    slot = now.replace(hour=POST_HOUR, minute=0, second=0, microsecond=0)
    return slot if slot - now > timedelta(minutes=30) else slot + timedelta(days=1)
