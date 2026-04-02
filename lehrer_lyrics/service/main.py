from __future__ import annotations

import random
import sqlite3
import zlib
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import markdown
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fasthtml.common import (
    Body,
    Footer,
    Head,
    Html,
    Link,
    Main,
    Meta,
    NotStr,
    Title,
    to_xml,
)

_SERVICE_DIR = Path(__file__).parent
_DB_PATH = _SERVICE_DIR / "songs.db"
_BERLIN = ZoneInfo("Europe/Berlin")
_PICO_CSS = Link(
    rel="stylesheet",
    href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css",
)
_LOCAL_CSS = Link(rel="stylesheet", href="/static/style.css")


def _today_berlin() -> date:
    return datetime.now(_BERLIN).date()


@lru_cache(maxsize=None)
def _all_songs() -> list[tuple[str, str | None, bytes]]:
    """Load all songs from songs.db once; returns (title, site_url, lyrics_gz) tuples."""
    conn = sqlite3.connect(_DB_PATH)
    try:
        rows = conn.execute(
            "SELECT title, site_url, lyrics_gz FROM songs ORDER BY slug"
        ).fetchall()
    finally:
        conn.close()
    return [(title, site_url, bytes(lyrics_gz)) for title, site_url, lyrics_gz in rows]


@lru_cache(maxsize=1)
def _render_page(today: date) -> str:
    """Render the HTML page for the daily song.

    ``lru_cache(maxsize=1)`` keeps exactly one entry keyed by ``today``.
    When the date rolls over the cache naturally misses and recomputes.
    """
    songs = _all_songs()
    random.seed(today.isoformat())
    title, site_url, lyrics_gz = random.choice(songs)
    lyrics_html = markdown.markdown(
        zlib.decompress(lyrics_gz).decode("utf-8"), extensions=["nl2br"]
    )
    footer_inner = (
        f'By Tom Lehrer &mdash; <a href="{site_url}">tomlehrersongs.com</a>'
        if site_url
        else "By Tom Lehrer"
    )
    return to_xml(
        Html(
            Head(
                Meta(charset="utf-8"),
                Meta(name="viewport", content="width=device-width, initial-scale=1"),
                _PICO_CSS,
                _LOCAL_CSS,
                Title(f"{title} — Tom Lehrer"),
            ),
            Body(
                Main(NotStr(lyrics_html), cls="container"),
                Footer(NotStr(footer_inner), cls="container"),
            ),
            lang="en",
        )
    )


app = FastAPI()
app.mount("/static", StaticFiles(directory=_SERVICE_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(content=_render_page(_today_berlin()))
