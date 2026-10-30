"""YouTube Shorts via the Data API v3 (OAuth installed-app flow).

Setup: create a Google Cloud project, enable "YouTube Data API v3", create an OAuth client of type
"Desktop app" and save its JSON as secrets/youtube_client_secret.json. Then connect each
language's channel once with `wiki-shorts connect-youtube --lang es`; the login is cached in
secrets/youtube_token.json (English) or secrets/youtube_token_es.json (Spanish), and so on. One
Google Cloud project serves every channel.

Uploads from an unverified project are locked to private until the project passes Google's
API audit, so request the audit early.
"""

from __future__ import annotations

import os
from datetime import timezone

from ..config import SECRETS_DIR
from .base import Post, Publisher

# readonly lets `connect-youtube` show which channel was picked, so a wrong pick is caught early.
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


class YouTube(Publisher):
    name = "youtube"

    @property
    def token_file(self):
        return SECRETS_DIR / f"youtube_token{self.lang.suffix.lower()}.json"

    def missing(self) -> list[str]:
        return [] if self.token_file.exists() else [
            f"{self.token_file.name} (run: wiki-shorts connect-youtube --lang {self.lang.code})"]

    def _service(self, login: bool = False):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        token, secret = self.token_file, SECRETS_DIR / "youtube_client_secret.json"
        creds = None if login or not token.exists() else \
            Credentials.from_authorized_user_file(str(token), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token.write_text(creds.to_json())
        if not creds or not creds.valid:
            if not login:
                raise SystemExit(f"YouTube isn't connected for {self.lang.name}. "
                                 f"Run: wiki-shorts connect-youtube --lang {self.lang.code}")
            if not secret.exists():
                raise SystemExit(f"Missing {secret}. See the YouTube section of the README.")
            flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
            creds = flow.run_local_server(port=0, prompt="select_account")
            SECRETS_DIR.mkdir(exist_ok=True)
            token.write_text(creds.to_json())
        return build("youtube", "v3", credentials=creds)

    def connect(self) -> str:
        """Log in (choosing the channel in the browser) and return the channel's name."""
        items = self._service(login=True).channels().list(part="snippet", mine=True).execute()
        return items["items"][0]["snippet"]["title"] if items.get("items") else "(no channel)"

    def _body(self, post: Post) -> dict:
        title = post.title if "#shorts" in post.title.lower() else f"{post.title} #Shorts"
        status = {"privacyStatus": os.getenv("YOUTUBE_PRIVACY", "public"),
                  "selfDeclaredMadeForKids": False,
                  "containsSyntheticMedia": True}  # AI voiceover: YouTube asks for disclosure
        if post.publish_at:
            # Scheduled videos must be uploaded private; YouTube makes them public at publishAt.
            status["privacyStatus"] = "private"
            status["publishAt"] = post.publish_at.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        return {
            # The language fields tell YouTube which audience to recommend the video to.
            "snippet": {"title": title[:100], "description": post.long_caption()[:5000],
                        "tags": post.hashtags[:15], "categoryId": "27",  # 27 = Education
                        "defaultLanguage": post.lang.youtube,
                        "defaultAudioLanguage": post.lang.youtube},
            "status": status,
        }

    def preview(self, post: Post) -> dict:
        return self._body(post)

    def publish(self, post: Post) -> str:
        from googleapiclient.http import MediaFileUpload

        request = self._service().videos().insert(
            part="snippet,status", body=self._body(post),
            media_body=MediaFileUpload(str(post.video), mimetype="video/mp4", chunksize=-1,
                                       resumable=True),
        )
        response = None
        while response is None:
            _, response = request.next_chunk()
        return f"https://youtube.com/shorts/{response['id']}"
