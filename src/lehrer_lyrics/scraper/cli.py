"""Typer CLI for the Tom Lehrer song scraper."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import typer

from lehrer_lyrics.scraper.fetcher import fetch_page
from lehrer_lyrics.scraper.parser import (
    extract_pdf_urls,
    extract_song_links,
    extract_song_title,
)

BASE_URL = "https://tomlehrersongs.com"
SONGS_URL = f"{BASE_URL}/songs/"

app = typer.Typer(help="Scrape Tom Lehrer song pages and collect PDF URLs.")


@app.command()
def scrape(
    cache_dir: Path = typer.Option(
        Path(".cache/html"),
        help="Directory for cached HTML files.",
    ),
    output: Path = typer.Option(
        Path("song-urls.json"),
        help="Output JSON file path.",
    ),
    delay: float = typer.Option(
        2.0,
        help="Seconds to wait between HTTP requests.",
        min=0.0,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-fetch pages even if they are already cached.",
    ),
) -> None:
    """Fetch all Tom Lehrer song pages and produce a JSON of PDF URLs."""
    last_request_time: list[float] = []

    typer.echo(f"Fetching main songs page: {SONGS_URL}")
    main_html = fetch_page(
        SONGS_URL, cache_dir, delay, force, _last_request_time=last_request_time
    )

    song_links = extract_song_links(main_html, BASE_URL)
    if not song_links:
        typer.echo("No song links found on the main page. Aborting.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Found {len(song_links)} song links. Fetching individual pages…")

    results: dict[str, dict[str, str]] = {}

    for _link_title, song_url in song_links:
        slug = urlparse(song_url).path.strip("/")
        typer.echo(f"  {slug}")

        song_html = fetch_page(
            song_url, cache_dir, delay, force, _last_request_time=last_request_time
        )

        title = extract_song_title(song_html) or _link_title
        pdf_urls = extract_pdf_urls(song_html, BASE_URL)

        results[title] = {"site": song_url, **pdf_urls}

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    typer.echo(f"\nWrote {len(results)} entries to {output}")
