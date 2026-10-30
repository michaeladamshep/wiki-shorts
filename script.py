"""Stage 2: turn the article into a timed voiceover script plus publishing metadata."""

from __future__ import annotations

from pydantic import BaseModel

from . import llm
from .config import MAX_WORDS, MIN_WORDS


class Beat(BaseModel):
    text: str
    visual_query: str
    wiki_image: str


class FactCheck(BaseModel):
    claim: str
    source_sentence: str


class Script(BaseModel):
    hook: str
    beats: list[Beat]
    payoff: str
    loop_line: str
    title: str
    description: str
    hashtags: list[str]
    x_post: str
    fact_checks: list[FactCheck]

    def sections(self) -> list[str]:
        """Narration in speaking order: hook, each beat, payoff + loop line."""
        return [self.hook, *[b.text for b in self.beats], f"{self.payoff} {self.loop_line}"]

    def narration(self) -> str:
        return " ".join(self.sections())

    def word_count(self) -> int:
        return len(self.narration().split())


def write(title: str, article: str, images: list[dict], topic: dict) -> Script:
    system = llm.prompt("write_script").format(min_words=MIN_WORDS, max_words=MAX_WORDS)
    image_list = "\n".join(f"- {i['file']}: {i['description']}" for i in images) or "(none)"
    angle = ""
    if topic.get("angle"):
        angle = (f"\nSuggested angle: {topic['angle']}"
                 f"\nSuggested hook: {topic['best_hook']}\n")
    user = (f"Article: {title}\n{angle}\nAvailable images:\n{image_list}\n\n"
            f"<article>\n{article}\n</article>")

    script = llm.ask(system, user, Script)
    for _ in range(2):
        n = script.word_count()
        if MIN_WORDS <= n <= MAX_WORDS:
            break
        print(f"  script is {n} words; asking for a rewrite to {MIN_WORDS}-{MAX_WORDS}")
        user_retry = (f"{user}\n\nYour previous script was {n} words, outside the required "
                      f"{MIN_WORDS}-{MAX_WORDS}. Previous script:\n{script.model_dump_json()}\n"
                      "Rewrite it to fit, keeping the strongest material.")
        script = llm.ask(system, user_retry, Script)

    known = {i["file"] for i in images}
    for beat in script.beats:
        if beat.wiki_image not in known:
            beat.wiki_image = ""
    return script
