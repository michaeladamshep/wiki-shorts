"""Stage 2b: adapt the fact-checked English script into another language."""

from __future__ import annotations

from pydantic import BaseModel

from . import llm
from .languages import Lang
from .script import Beat, Script

MAX_SECONDS = 60  # longer translations get tightened after the voiceover is measured


class Translation(BaseModel):
    hook: str
    beats: list[str]
    payoff: str
    loop_line: str
    title: str
    description: str
    hashtags: list[str]
    x_post: str
    back_translation: str


def translate(english: Script, lang: Lang, local_title: str | None,
              previous: Script | None = None, seconds: float | None = None) -> tuple[Script, str]:
    """Return the translated script (visual cues and fact checks kept from English) and an
    English back-translation of its narration. Pass `previous` and its spoken `seconds` to get a
    shorter version of a translation that ran too long."""
    system = llm.prompt("translate_script").format(
        language=lang.name, style=lang.style, beats=len(english.beats), max_seconds=MAX_SECONDS,
        max_words=lang.max_words)
    title_note = (f"{lang.name} Wikipedia title: {local_title}" if local_title
                  else f"(No {lang.name} Wikipedia article exists.)")
    user = f"{title_note}\n\nEnglish script:\n{english.model_dump_json(exclude={'fact_checks'})}"
    if previous is not None:
        # A concrete word limit, from this voice's measured pace, gets followed far more
        # reliably than "cut about 10%".
        words = previous.word_count()
        limit = int(words * (MAX_SECONDS - 3) / seconds)
        user += (f"\n\nYour previous {lang.name} version has {words} words and runs "
                 f"{seconds:.0f} seconds when spoken, over the {MAX_SECONDS}-second limit. "
                 f"Previous version:\n{previous.model_dump_json(exclude={'fact_checks'})}\n"
                 f"Rewrite it in at most {limit} words in total across hook, beats, payoff and "
                 "loop line. Drop the least important details and filler words; "
                 "keep the hook, the strongest reveals and the loop line.")

    # Medium effort: adapting a finished script needs less reasoning than writing one.
    result = llm.ask(system, user, Translation, effort="medium")
    if len(result.beats) != len(english.beats):
        user += (f"\n\nYou returned {len(result.beats)} beats; return exactly "
                 f"{len(english.beats)}, one per English beat.")
        result = llm.ask(system, user, Translation, effort="medium")
        if len(result.beats) != len(english.beats):
            raise RuntimeError(f"{lang.name} translation has {len(result.beats)} beats, "
                               f"expected {len(english.beats)}")

    script = english.model_copy(update={
        "hook": result.hook, "payoff": result.payoff, "loop_line": result.loop_line,
        "beats": [Beat(text=text, visual_query=b.visual_query, wiki_image=b.wiki_image)
                  for text, b in zip(result.beats, english.beats)],
        "title": result.title, "description": result.description,
        "hashtags": result.hashtags, "x_post": result.x_post,
    })
    return script, result.back_translation
