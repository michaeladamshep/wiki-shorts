"""Stage 1: pick an article likely to make a high-retention short."""

from __future__ import annotations

import random

from pydantic import BaseModel

from . import llm, wiki
from .config import HISTORY_FILE, read_json

MIN_ARTICLE_BYTES = 12_000  # ~1,500+ words of prose; stubs make thin videos
POOL_SIZES = {"unusual": 18, "featured": 8, "trending": 6}


class Score(BaseModel):
    title: str
    curiosity: int
    hook_strength: int
    visual: int
    brand_safe: bool
    best_hook: str
    angle: str


class Scores(BaseModel):
    candidates: list[Score]


def used_titles() -> set[str]:
    return {entry["title"] for entry in read_json(HISTORY_FILE, [])}


def candidate_pool() -> list[dict]:
    """Sample candidates from sources that skew interesting, then drop stubs and repeats."""
    used = used_titles()
    sources = {
        "unusual": wiki.page_links("Wikipedia:Unusual articles"),
        "featured": wiki.page_links("Wikipedia:Featured articles"),
    }
    try:
        sources["trending"] = wiki.top_viewed()
    except Exception as e:  # pageview data lags a day or two; not essential
        print(f"  (skipping trending: {e})")

    picked: list[str] = []
    for name, titles in sources.items():
        fresh = [t for t in titles if t not in used]
        picked += random.sample(fresh, min(POOL_SIZES[name] * 2, len(fresh)))

    pages = [p for p in wiki.summaries(picked) if p["length"] >= MIN_ARTICLE_BYTES]
    random.shuffle(pages)
    return pages[:sum(POOL_SIZES.values())]


def pick(override: str | None = None) -> dict:
    if override:
        title, _ = wiki.full_text(override)
        return {"title": title, "angle": "", "best_hook": "", "score": None,
                "source": "manual"}

    pool = candidate_pool()
    if not pool:
        raise SystemExit("No candidates found. Check your network connection.")
    listing = "\n\n".join(f"### {p['title']}\n{p['intro'][:700]}" for p in pool)
    scores = llm.ask(llm.prompt("score_topic"),
                     f"Score every candidate below.\n\n{listing}", Scores, effort="medium")

    titles = {p["title"] for p in pool}
    ranked = sorted(
        (s for s in scores.candidates if s.brand_safe and s.title in titles),
        key=lambda s: s.curiosity * 2 + s.hook_strength * 2 + s.visual,
        reverse=True,
    )
    if not ranked:
        raise SystemExit("Claude rejected every candidate; run again for a fresh pool.")
    best = ranked[0]
    return {"title": best.title, "angle": best.angle, "best_hook": best.best_hook,
            "score": best.model_dump(), "source": "auto",
            "runners_up": [s.title for s in ranked[1:6]]}
