# wiki-shorts

Picks an interesting Wikipedia article, writes a ~55-second script, voices it with Microsoft's free neural
voices (edge-tts, no API key), cuts
it to Wikimedia images and Pexels stock clips with burned-in word-by-word captions, and posts the
1080×1920 MP4 to YouTube Shorts, TikTok, Instagram Reels, Facebook Reels and X.

Each video is also adapted into Spanish (Latin America), Portuguese (Brazil), Hindi, Indonesian
and Arabic, voiced by a native neural voice, and posted to **that language's own accounts**.

## Setup

```sh
brew install ffmpeg-full uv     # ffmpeg-full includes libass, which captions need
uv sync
cp .env.example .env            # then fill in the keys
```

Optional: drop royalty-free music (`.mp3`/`.m4a`/`.wav`) into `music/`. A random track is mixed in
under the voice and ducks whenever the narrator speaks. Use `--no-music` to skip it.

## Use

```sh
uv run wiki-shorts make                          # auto-pick a topic, then stop for review
uv run wiki-shorts make --topic "Tunguska event" # use a specific article
uv run wiki-shorts publish 2026-10-14-tunguska-event --dry-run
uv run wiki-shorts publish 2026-10-14-tunguska-event              # all platforms
uv run wiki-shorts publish 2026-10-14-tunguska-event --only youtube,tiktok
uv run wiki-shorts resume 2026-10-14-tunguska-event               # finish a failed run
uv run wiki-shorts make --auto                   # no review step (for scheduled runs)
uv run wiki-shorts make --langs es,pt            # only these translations (--langs none: English only)
uv run wiki-shorts translate 2026-10-14-tunguska-event --langs hi # add translations to a finished run
uv run wiki-shorts publish 2026-10-14-tunguska-event --langs es   # just the Spanish accounts
uv run wiki-shorts publish 2026-10-14-tunguska-event --schedule   # YouTube at 7pm in each audience's time zone
uv run wiki-shorts connect-youtube --lang es     # log in to the Spanish channel (once)
```

`make` prints the script and a **fact-check list**, where every claim is paired with the article
sentence that supports it. Check it before publishing. Platforms penalise accounts that spread
inaccurate AI content, and that's the main risk with `--auto`.

## How it works

Each run lives in `runs/<date>-<slug>/`, and each stage writes its output there. `resume` skips
any stage whose file already exists, so to redo a stage, delete its file and resume.

| Stage | Output | Notes |
|---|---|---|
| Topic | `topic.json` | Samples ~30 candidates from Wikipedia:Unusual articles, Featured articles and yesterday's most-viewed pages, drops stubs and repeats (`history.json`), and Claude scores each one for curiosity, hook strength, visual potential and brand safety |
| Article | `article.txt`, `images.json` | Freely licensed JPEG/PNG images only (PD, CC0, CC BY, CC BY-SA) |
| Script | `script.json` | Hook ≤ 12 words, 5–7 escalating beats, payoff, and a loop line that runs back into the hook. 130–165 words, re-prompted if outside that range |
| Voice | `voice.mp3`, `words.json` | edge-tts word timings, aligned back onto the script's own words (keeping punctuation) for captions and cuts. Change voice with `TTS_VOICE` |
| Visuals | `shots.json`, `credits.json`, `assets/` | Alternates article images and Pexels clips every ~3s, with faster cuts during the hook |
| Render | `final.mp4`, `thumb.jpg` | Ken Burns stills on blurred fill, 9:16 crops, ASS captions, loudness normalised to −14 LUFS |
| Translate | `<lang>/script.json`, `<lang>/translation.json` | Claude adapts the fact-checked English script (same beats, same facts, native hashtags and title) and returns an English back-translation for review. Shortened and re-voiced if it runs over 60s |
| Translated video | `<lang>/final.mp4` | Native edge-tts voice, same images re-timed to the new voiceover, captions in Noto fonts for Hindi and Arabic (`fonts/`, SIL OFL) |
| Publish | `posts.json` | Posting is idempotent: platforms already in `posts.json` are skipped |

Prompts live in `prompts/`. Tune them there, not in code.

## Languages and audiences

| Code | Language | Voice | Audience time zone | Notes |
|---|---|---|---|---|
| `es` | Spanish (Latin America) | es-MX-JorgeNeural | Mexico City | YouTube language `es-419` |
| `pt` | Portuguese (Brazil) | pt-BR-AntonioNeural | São Paulo | |
| `hi` | Hindi | hi-IN-MadhurNeural | Kolkata | TikTok skipped: banned in India |
| `id` | Indonesian | id-ID-ArdiNeural | Jakarta | |
| `ar` | Arabic (Modern Standard) | ar-EG-ShakirNeural | Cairo | |

Settings live in `src/wiki_shorts/languages.py`. Change a voice with `TTS_VOICE_<CODE>` and the
default set with `LANGS=es,pt` in `.env`.

What gets each translation in front of the right people:

- **Its own accounts.** Each language posts only to accounts set up for it. Account settings take
  the language code as a suffix (`TIKTOK_ACCESS_TOKEN_ES`, `META_PAGE_ID_HI`,
  `UPLOAD_POST_USER_AR`, ...; the unsuffixed ones are English). A language with no account on a
  platform is skipped, never posted to the English account: a mixed-language account confuses
  every platform's recommendations.
- **Native language throughout:** voice, captions, title, description and hashtags people in
  that market search for.
- **YouTube language metadata** (`defaultLanguage`, `defaultAudioLanguage`).
- **Local posting time** with `publish --schedule` (YouTube only; the other APIs have no
  scheduling, so run `publish` at the audience's evening, or schedule it later in GitHub Actions).

TikTok, Instagram, Facebook and X have no API setting for audience language or country. They
decide from the account, the spoken and written language, and who engages first, which is why
separate accounts matter. Set each account's profile language, name and bio in its target
language.

## Platform setup

Every platform requires a developer app. Some require review before public posting, so start
those early. Until a platform is approved, set `PUBLISH_<PLATFORM>=aggregator` to post through
[Upload-Post](https://upload-post.com) with one API key.

**YouTube.** In Google Cloud Console, create a project, enable *YouTube Data API v3* and create an
OAuth client ID of type *Desktop app*. Save the JSON as `secrets/youtube_client_secret.json`.
Then run `wiki-shorts connect-youtube --lang en` (and `--lang es`, ... for each language's
channel) and pick that channel in the browser. One project serves every channel. **Uploads from unverified projects are forced to
private** until the project passes the YouTube API compliance audit. The default quota is roughly
6 uploads a day.

**TikTok.** On developers.tiktok.com, create an app with *Content Posting API* (Direct Post) and the
`video.publish` scope, then get a user access token through Login Kit and put it in
`TIKTOK_ACCESS_TOKEN`. Tokens expire after 24 hours. **Unaudited apps can post only privately**
(SELF_ONLY), so apply for the audit.

**Instagram and Facebook.** You need an Instagram Business or Creator account linked to a Facebook
Page. Create a Meta app (Business type), add *Instagram Graph API* and *Facebook Login for
Business*, and request `instagram_content_publish`, `instagram_basic`, `pages_manage_posts`,
`pages_read_engagement` and `pages_show_list`. Generate a long-lived Page token and set
`META_PAGE_TOKEN`, `META_PAGE_ID` and `META_IG_USER_ID` (one Page and Instagram account per
language, with `_ES`, `_PT`, ... versions of each setting). Posting to your own accounts works in
development mode; app review is needed only for other people's accounts.

**X.** Posting with media needs a paid or pay-per-use API plan. Create an app with OAuth 2.0 user
auth and the `tweet.write users.read media.write` scopes, then put a user access token in
`X_ACCESS_TOKEN`. X's media endpoints have changed several times, so if an upload fails, compare
`publish/x.py` against the current v2 media upload docs.

## Content rules this follows

- Wikipedia text is CC BY-SA, so every description links the source article and credits each
  image's author and licence.
- The narration is AI-generated, so YouTube's `containsSyntheticMedia` and TikTok's `is_aigc` flags
  are set.
- The topic prompt rejects recent tragedies, private individuals and partisan politics, which are
  brand-unsafe and get suppressed.
