"""wiki-shorts CLI: `make` a video (plus translations), `resume` a failed run, `publish` a finished one.

A run folder holds the English video at its top level and each translation in a subfolder named
for its language (runs/<run>/es/final.mp4).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Optional
from urllib.parse import quote

import typer

from . import captions, languages, render, topics, visuals, voice, wiki
from .config import HISTORY_FILE, RUNS_DIR, read_json, write_json
from .languages import LANGUAGES, Lang
from .publish import PLATFORMS, Post, publisher
from .publish.youtube import YouTube
from .script import Script, write
from .translate import MAX_SECONDS, translate

ENGLISH = LANGUAGES["en"]

app = typer.Typer(add_completion=False, no_args_is_help=True)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def resolve_run(run: str) -> Path:
    path = Path(run)
    if not path.is_absolute():
        path = RUNS_DIR / run if (RUNS_DIR / run).exists() else Path.cwd() / run
    if not path.exists():
        raise typer.BadParameter(f"No run at {path}")
    return path


def build(run_dir: Path, music: bool) -> Path:
    """Run every stage that hasn't produced its output yet."""
    topic = read_json(run_dir / "topic.json")

    if not (run_dir / "article.txt").exists():
        typer.echo("• fetching article + images")
        title, text = wiki.full_text(topic["title"])
        (run_dir / "article.txt").write_text(text)
        write_json(run_dir / "images.json", wiki.free_images(title))
    article = (run_dir / "article.txt").read_text()
    images = read_json(run_dir / "images.json", [])

    if not (run_dir / "script.json").exists():
        typer.echo("• writing script")
        write_json(run_dir / "script.json",
                   write(topic["title"], article, images, topic).model_dump())
    script = Script.model_validate(read_json(run_dir / "script.json"))
    typer.echo(f"  {script.word_count()} words: {script.hook}")

    if not (run_dir / "words.json").exists():
        typer.echo("• generating voiceover")
        write_json(run_dir / "words.json", voice.synthesize(script.narration(), run_dir))
    words = read_json(run_dir / "words.json")
    return finish(run_dir, run_dir, script, words, images, ENGLISH, music)


def build_lang(run_dir: Path, lang: Lang, music: bool) -> Path:
    """Translate the English script, voice it natively and render it into runs/<run>/<lang>/."""
    out = lang_dir(run_dir, lang)
    out.mkdir(exist_ok=True)
    english = Script.model_validate(read_json(run_dir / "script.json"))
    meta_file = out / "translation.json"

    if not (out / "script.json").exists():
        typer.echo(f"• translating into {lang.name}")
        local = wiki.local_title(read_json(run_dir / "topic.json")["title"], lang.wiki)
        script, back = translate(english, lang, local)
        write_json(out / "script.json", script.model_dump())
        write_json(meta_file, {"local_title": local, "back_translation": back})
    script = Script.model_validate(read_json(out / "script.json"))

    if not (out / "words.json").exists():
        typer.echo(f"• generating {lang.name} voiceover ({lang.tts_voice})")
        words = voice.synthesize(script.narration(), out, lang.tts_voice)
        for _ in range(2):
            seconds = words[-1]["end"]
            if seconds <= MAX_SECONDS:
                break
            typer.echo(f"  {seconds:.0f}s is over {MAX_SECONDS}s; asking for a shorter version")
            meta = read_json(meta_file)
            script, back = translate(english, lang, meta["local_title"], script, seconds)
            write_json(out / "script.json", script.model_dump())
            write_json(meta_file, {**meta, "back_translation": back})
            words = voice.synthesize(script.narration(), out, lang.tts_voice)
        write_json(out / "words.json", words)
        # A new voiceover changes every timing, so shots and video from an old one are stale.
        for stale in ("shots.json", "credits.json", "final.mp4"):
            (out / stale).unlink(missing_ok=True)
    words = read_json(out / "words.json")
    images = read_json(run_dir / "images.json", [])
    # Images download into the run's shared assets/ folder, so each one is fetched only once.
    return finish(out, run_dir, script, words, images, lang, music)


def finish(out: Path, run_dir: Path, script: Script, words: list[dict], images: list[dict],
           lang: Lang, music: bool) -> Path:
    """Plan the shots against this voiceover's timing, then render. Shared by every language."""
    if not (out / "shots.json").exists():
        typer.echo("• gathering visuals")
        spans = voice.section_times(script.sections(), words)
        beats = script.beats
        # Hook borrows the first beat's visuals; payoff borrows the last beat's.
        guides = [beats[0], *beats, beats[-1]]
        sections = [{"start": s, "end": e, "visual_query": g.visual_query,
                     "wiki_image": g.wiki_image if 0 < i < len(guides) - 1 else ""}
                    for i, ((s, e), g) in enumerate(zip(spans, guides))]
        shots, credits = visuals.build(sections, images, run_dir)
        write_json(out / "shots.json", shots)
        write_json(out / "credits.json", credits)
    shots = read_json(out / "shots.json")

    final = out / "final.mp4"
    if not final.exists():
        typer.echo(f"• rendering {len(shots)} shots")
        captions.write_ass(words, out / "captions.ass", lang.font, lang.font_size)
        total = shots[-1]["start"] + shots[-1]["duration"]
        render.render(shots, out, total, music=music, fonts_dir=lang.fonts_dir)
    return final


def lang_dir(run_dir: Path, lang: Lang) -> Path:
    return run_dir if lang.code == "en" else run_dir / lang.code


def translated(run_dir: Path) -> list[Lang]:
    """Languages this run already has a translation folder for."""
    return [LANGUAGES[c] for c in languages.TRANSLATIONS if (run_dir / c).is_dir()]


def build_translations(run_dir: Path, langs: list[Lang], music: bool) -> None:
    for lang in langs:
        try:
            build_lang(run_dir, lang, music)
        except Exception as e:  # one language failing shouldn't stop the others
            typer.secho(f"  ✗ {lang.name}: {e}  (retry with: wiki-shorts resume {run_dir.name})",
                        fg="red")


def post_for(run_dir: Path, lang: Lang = ENGLISH) -> Post:
    folder = lang_dir(run_dir, lang)
    script = Script.model_validate(read_json(folder / "script.json"))
    title = read_json(run_dir / "topic.json")["title"]
    return Post(
        video=folder / "final.mp4", thumb=folder / "thumb.jpg", title=script.title,
        description=script.description, hashtags=script.hashtags, x_post=script.x_post,
        # Translations are adapted from the English article, so that stays the credited source.
        source_url=f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
        credits=read_json(folder / "credits.json", []), lang=lang,
    )


def review(run_dir: Path, final: Path) -> None:
    script = Script.model_validate(read_json(run_dir / "script.json"))
    typer.echo(f"\n✔ {final}  ({render.duration(final):.1f}s)\n")
    typer.echo(f"Title: {script.title}\n\n{script.narration()}\n")
    typer.echo("Fact-check before posting:")
    for fc in script.fact_checks:
        typer.echo(f"  • {fc.claim}\n      ↳ “{fc.source_sentence}”")
    for lang in translated(run_dir):
        out = run_dir / lang.code
        if not (out / "final.mp4").exists():
            typer.secho(f"\n✗ {lang.name}: not finished", fg="red")
            continue
        seconds = render.duration(out / "final.mp4")
        meta = read_json(out / "translation.json", {})
        flag = "  ⚠ long" if seconds > MAX_SECONDS + 2 else ""
        typer.echo(f"\n✔ {lang.name}: {out / 'final.mp4'}  ({seconds:.1f}s){flag}")
        typer.echo(f"  Title: {Script.model_validate(read_json(out / 'script.json')).title}")
        typer.echo(f"  Back-translation (check that no fact changed):\n  {meta.get('back_translation', '')}")
    typer.echo(f"\nWhen it looks right:  wiki-shorts publish {run_dir.name}")


def do_publish(run_dir: Path, langs: list[Lang], only: list[str], dry_run: bool,
               schedule: bool = False) -> None:
    for lang in langs:
        folder = lang_dir(run_dir, lang)
        typer.secho(f"— {lang.name} —", bold=True)
        if not (folder / "final.mp4").exists():
            typer.echo(f"  no {lang.name} video in this run; skipping")
            continue
        post = post_for(run_dir, lang)
        if schedule:
            post.publish_at = languages.next_post_time(lang)
            typer.echo(f"  YouTube scheduled for {post.publish_at:%a %H:%M} {lang.tz} "
                       f"({post.publish_at.astimezone():%a %H:%M} your time)")
        publish_platforms(folder, post, only, dry_run)


def publish_platforms(folder: Path, post: Post, only: list[str], dry_run: bool) -> None:
    lang = post.lang
    posts_file = folder / "posts.json"
    posts = read_json(posts_file, {})
    for platform in only:
        if platform in lang.skip:
            typer.echo(f"  {platform}: skipped, it doesn't reach the {lang.name} audience")
            continue
        if platform in posts and not dry_run:
            typer.echo(f"  {platform}: already posted → {posts[platform]['url']}")
            continue
        pub = publisher(platform, lang)
        if dry_run:
            typer.echo(f"--- {pub.name} ---\n{json.dumps(pub.preview(post), indent=2, ensure_ascii=False)}")
            continue
        if missing := pub.missing():
            typer.secho(f"  {platform}: no {lang.name} account set up yet; add {', '.join(missing)}",
                        fg="yellow")
            continue
        typer.echo(f"• posting to {pub.name}")
        try:
            url = pub.publish(post)
        except Exception as e:  # keep going so one broken platform doesn't block the rest
            typer.secho(f"  ✗ {platform}: {e}", fg="red")
            continue
        posts[platform] = {"url": url, "at": datetime.now().isoformat(timespec="seconds")}
        write_json(posts_file, posts)
        typer.secho(f"  ✔ {url}", fg="green")


def parse_only(only: Optional[str]) -> list[str]:
    chosen = [p.strip().lower() for p in only.split(",")] if only else PLATFORMS
    bad = [p for p in chosen if p not in PLATFORMS]
    if bad:
        raise typer.BadParameter(f"Unknown platform(s): {', '.join(bad)}. Use {', '.join(PLATFORMS)}")
    return chosen


@app.command()
def make(
    topic: Annotated[Optional[str], typer.Option(help="Use this Wikipedia title instead of auto-picking")] = None,
    auto: Annotated[bool, typer.Option(help="Publish immediately, skipping the review step")] = False,
    only: Annotated[Optional[str], typer.Option(help="Comma-separated platforms for --auto")] = None,
    music: Annotated[bool, typer.Option(help="Mix in a random track from music/")] = True,
    langs: Annotated[Optional[str], typer.Option(
        help="Translations to make, e.g. es,pt (default: LANGS in .env, else all; 'none' to skip)")] = None,
) -> None:
    """Pick a topic, write, voice, render, translate, and (with --auto) publish a new video."""
    typer.echo("• choosing topic" if not topic else f"• using topic {topic!r}")
    chosen = topics.pick(topic)
    typer.echo(f"  → {chosen['title']}" + (f": {chosen['angle']}" if chosen.get("angle") else ""))

    run_dir = RUNS_DIR / f"{date.today():%Y-%m-%d}-{slugify(chosen['title'])}"
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "topic.json", chosen)
    history = read_json(HISTORY_FILE, [])
    history.append({"title": chosen["title"], "date": date.today().isoformat(), "run": run_dir.name})
    write_json(HISTORY_FILE, history)

    final = build(run_dir, music)
    targets = languages.parse(langs, languages.default_translations())
    build_translations(run_dir, targets, music)
    review(run_dir, final)
    if auto:
        do_publish(run_dir, [ENGLISH, *translated(run_dir)], parse_only(only), dry_run=False)


@app.command()
def resume(
    run: Annotated[str, typer.Argument(help="Run folder name under runs/")],
    music: bool = True,
) -> None:
    """Finish a run that stopped partway, translations included. Delete a stage's output file to
    redo that stage."""
    run_dir = resolve_run(run)
    final = build(run_dir, music)
    build_translations(run_dir, translated(run_dir), music)
    review(run_dir, final)


@app.command(name="translate")
def translate_cmd(
    run: Annotated[str, typer.Argument(help="Run folder name under runs/")],
    langs: Annotated[Optional[str], typer.Option(help="e.g. es,pt (default: all)")] = None,
    music: bool = True,
) -> None:
    """Add translated videos to an existing run."""
    run_dir = resolve_run(run)
    build_translations(run_dir, languages.parse(langs, languages.TRANSLATIONS), music)
    review(run_dir, run_dir / "final.mp4")


@app.command()
def publish(
    run: Annotated[str, typer.Argument(help="Run folder name under runs/")],
    only: Annotated[Optional[str], typer.Option(help=f"Comma-separated subset of: {', '.join(PLATFORMS)}")] = None,
    dry_run: Annotated[bool, typer.Option(help="Print each platform's payload without posting")] = False,
    langs: Annotated[Optional[str], typer.Option(
        help="Languages to post, e.g. en,es (default: English plus every translation in the run)")] = None,
    schedule: Annotated[bool, typer.Option(
        help="Schedule YouTube uploads for the evening in each audience's time zone")] = False,
) -> None:
    """Post a finished video, each language to its own accounts. Platforms that already
    succeeded are skipped."""
    run_dir = resolve_run(run)
    chosen = languages.parse(langs, ["en", *[l.code for l in translated(run_dir)]])
    do_publish(run_dir, chosen, parse_only(only), dry_run, schedule)


@app.command(name="connect-youtube")
def connect_youtube(
    lang: Annotated[str, typer.Option(help="Language whose channel to connect, e.g. es")] = "en",
) -> None:
    """Log in to one language's YouTube channel. Pick that channel in the browser window."""
    target = languages.get(lang)
    name = YouTube(target).connect()
    typer.secho(f"✔ {target.name} uploads will go to the YouTube channel “{name}”", fg="green")


if __name__ == "__main__":
    app()
