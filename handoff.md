# wiki-shorts handoff

_As of 2026-10-29_

## Goal

Automatically turn interesting Wikipedia articles into 30–60 second vertical videos (1080×1920) and
post them to YouTube Shorts, TikTok, Instagram Reels, Facebook Reels and X. Topics should be the kind
that hold attention on short-form platforms: mysteries, bizarre history, disasters and survival
stories, weird nature, extreme records.

The project lives in its own repo at `~/Documents/GitHub/wiki-shorts`, separate from the
headgonebynoise.com site (`glowing-journey`).

## Decisions

| Area | Choice | Why |
|---|---|---|
| Language and tooling | Python 3.12 with `uv` and a `typer` CLI | Media libraries lack reliable wheels for the system Python 3.14 |
| Topic picking | Sample ~30 candidates from Wikipedia:Unusual articles, Featured articles and top-viewed pages; Claude scores them | `Special:Random` mostly returns stubs |
| LLM | `claude-opus-5-5` (set in `.env`; the code default is still `claude-opus-5`) through structured outputs, with server-side refusal fallbacks enabled | Default from the Claude API guidance. Override with `CLAUDE_MODEL` |
| Voice | **edge-tts** (Microsoft neural voices, free, no key), voice `en-US-AndrewNeural` at +8% speed | Switched from ElevenLabs on 2026-10-16 at Michael's request |
| Visuals | Freely licensed Wikimedia images from the article, plus Pexels portrait stock clips, alternating every ~3s | Free. Licences are tracked for attribution |
| Rendering | ffmpeg from Homebrew's **`ffmpeg-full`** formula | The plain `ffmpeg` formula lacks libass, which burning captions in requires |
| Captions | ASS subtitles with 1–3 words on screen and the spoken word highlighted in yellow | Standard short-form style |
| Publishing | Native API module per platform, with an Upload-Post aggregator fallback (`PUBLISH_<PLATFORM>=aggregator`) | Michael chose to auto-post everywhere. The aggregator covers platforms whose app review is still pending |
| Languages | English plus Spanish (LatAm), Portuguese (BR), Hindi, Indonesian and Arabic, chosen 2026-10-29 as the largest short-form audiences outside English | Each is adapted from the fact-checked English script, not from the local Wikipedia |
| Audience targeting | **One set of accounts per language**, never falling back to the English accounts. Native voice, captions, title and hashtags; YouTube language metadata; optional YouTube scheduling for 7pm in the audience's time zone; Hindi skips TikTok (banned in India) | Michael chose separate accounts. No platform API offers audience targeting for organic posts, so the account itself is the main signal |
| Safety | `make` stops for human review by default and prints a fact-check list. `--auto` skips it | Auto-posting unchecked AI-generated facts risks account penalties |
| Deployment (planned) | Run locally at first, then GitHub Actions: a scheduled `make` job that opens a review issue, plus a manual `publish` workflow | Matches the site's existing cron workflow, and keeps a review step |

## What's done

- **Full pipeline written:** topic → article and images → script → voice → visuals → render →
  publish. Each run writes to `runs/<date>-<slug>/`, and `resume` skips any stage whose output
  file already exists.
- **Verified working:**
  - Wikipedia fetching: candidate lists, summaries, full text, and image licence filtering
  - Rendering at 1080×1920 and 30fps: slow pan and zoom on photos, blurred background behind them,
    clips cropped to vertical, burned-in captions. Loudness lands at about −15.5 LUFS against a −14 target
  - edge-tts voice with word timings. Its timings are aligned back onto the script's own words,
    including when it reports several words as one (it reported "In 1518" that way)
  - Shot planning: images and clips alternate, with faster cuts during the opening line
  - `publish --dry-run` payloads for YouTube, TikTok and X
- **iCloud fix:** `~/Documents` is synced by iCloud Drive, which was hiding files in the Python
  environment and breaking imports at random. The environment now lives in `.venv.nosync` (iCloud
  skips that suffix), with a `.venv` symlink pointing to it.
- **Translations (2026-10-29):** `languages.py` (per-language voice, font, time zone, dialect
  notes, skipped platforms), `translate.py` + `prompts/translate_script.md` (one Claude call per
  language, plus an English back-translation for review), and translated videos rendered into
  `runs/<run>/<lang>/`. Commands: `make --langs`, `translate`, `publish --langs/--schedule`,
  `connect-youtube --lang`. Hindi and Arabic captions use bundled Noto Black fonts in `fonts/`
  (SIL OFL), verified to render (Arabic shapes and runs right to left).
  - Fixed: the word-timing alignment discarded every non-ASCII letter, which would have broken
    captions for Hindi, Arabic and accented words.
  - Translations run longer than English (Spanish 153 words = 64s vs English 156 = 57s), so a
    voiceover over 60s is sent back to Claude with a word limit based on the measured pace.
  - edge-tts is flaky in three ways, all seen on 2026-10-29: "No audio was received", a stream
    that stalls forever, and a stream that ends early with no error (the Arabic audio stopped
    halfway and the missing words got guessed timings). `voice.synthesize` now caps each
    request at 3 minutes and retries when the spoken words cover under 90% of the script.
  - Measured pace sets each language's `max_words` (es 125, pt 120, hi 115, id 125, ar 95), so
    translations rarely need a shortening round. Translation calls run at medium effort.
- **Translations verified (2026-10-29):** Tunguska in all five languages, 58–60s each,
  back-translations checked, Arabic and Hindi caption rendering checked frame by frame. A
  real `publish` with no per-language accounts skipped every platform without touching the
  English accounts.
- **Docs:** `README.md` covers setup, usage and the developer-app requirements for each platform.
  `.env.example` lists every setting.

## Not yet tested live

- Claude topic scoring and script writing (no key was available until now)
- Pexels clip search and download
- All five platform uploaders, which were written from API docs and have never posted. X is the most
  likely to need fixes because its media upload API changes often.

## Current state

- `.env` exists, and git ignores it. `ANTHROPIC_API_KEY` is filled in. `PEXELS_API_KEY` is empty
  because Pexels has paused new API key issuance (2026-10-16). It's now optional: without it,
  `visuals.py` uses article images only and cycles through them. Michael chose to keep it image-only
  for now (no Pixabay). `WIKI_USER_AGENT` is set.
- One run so far, `runs/2026-10-16-tunguska-event/`, with English plus all five translations
  (`es/`, `pt/`, `hi/`, `id/`, `ar/`).
  Nothing has been published. The English video has visuals problems: an off-topic image (Tesla's
  Wardenclyffe Tower) under the hook, and images cycling back unrelated to the narration.
- **The repo has no commits.** All files are untracked, and there's no GitHub remote.

## Next steps

1. Put an email in `WIKI_USER_AGENT` in `.env`. Add a Pexels key if issuance reopens, or add
   another stock-clip source (e.g. Pixabay's video API) if image-only videos look too static.
2. Make the first video with `uv run wiki-shorts make --topic "Tunguska event"`. Fix whichever
   stage fails on its first live call, then use `resume`.
3. Run `uv run wiki-shorts make` with no topic two or three times to judge topic quality. Tune
   `prompts/score_topic.md` and `prompts/write_script.md` as needed.
4. Make the initial commit and push to a private GitHub repo.
5. Create the per-language accounts (YouTube channel, TikTok, Instagram + Facebook Page, X for
   each of es, pt, hi, id, ar; Hindi needs no TikTok), then add their `_ES`/`_PT`/... settings
   to `.env` and run `connect-youtube --lang <code>` for each channel.
6. Start platform developer apps early, because the reviews take a while:
   - **YouTube:** the API audit. Until it passes, uploads stay private.
   - **TikTok:** the Content Posting API audit. Until it passes, posts are visible only to you.
   - **Meta:** create the Instagram and Facebook app and a long-lived Page access token.
   - **X:** posting with media needs a paid API plan.
7. Once videos look right, move to GitHub Actions. That needs:
   - a bundled open-licence Latin caption font, replacing macOS's Arial Black (Hindi and Arabic
     already use bundled fonts)
   - per-language publish jobs on cron at each audience's evening, since only YouTube's API can
     schedule
   - the `.env` keys and the YouTube login file stored as GitHub secrets
   - the YouTube OAuth consent screen set to "In production"
   - a TikTok token-refresh step
   - `history.json` committed back after each run
8. Optional: add royalty-free music to `music/`, and try other voices (`uv run edge-tts --list-voices`).

## Gotchas

- Use `ffmpeg-full`; `config.ffmpeg_bin()` prefers it automatically.
- Don't recreate `.venv` as a real folder inside iCloud-synced `~/Documents`. Keep the `.nosync` symlink.
- Wikipedia text is CC BY-SA. Post descriptions must keep the source link and image credits,
  which `publish/base.py` builds from `credits.json`.
- The YouTube and TikTok uploads set the AI-content disclosure flags (`containsSyntheticMedia` and
  `is_aigc`).
