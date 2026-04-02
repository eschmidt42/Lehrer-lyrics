"""Typer CLI for the Tom Lehrer song scraper."""

from __future__ import annotations

import json
import time
from pathlib import Path

import typer
from rich.console import Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from lehrer_lyrics.scraper.fetcher import fetch_page
from lehrer_lyrics.scraper.parser import (
    extract_pdf_urls,
    extract_song_links,
    extract_song_title,
)

BASE_URL = "https://tomlehrersongs.com"
SONGS_URL = f"{BASE_URL}/songs/"
_WINDOW_SIZE = 10

app = typer.Typer(help="Scrape Tom Lehrer song pages and collect PDF URLs.")


class _LiveDisplay:
    """Live-renderable combining a rolling song window with an overall progress bar.

    The rolling window shows the last ``_WINDOW_SIZE`` songs:
    - spinner  — the song currently being fetched
    - ✓ (green) — songs already processed

    A progress bar below shows overall N/total, time elapsed, and ETA.
    """

    def __init__(self, progress: Progress) -> None:
        self.progress = progress
        self._spinner = Spinner("dots")
        self._window: list[tuple[str, bool]] = []  # (title, is_done)

    def set_current(self, title: str) -> None:
        """Add a new in-progress entry, evicting the oldest if the window is full."""
        if len(self._window) >= _WINDOW_SIZE:
            self._window.pop(0)
        self._window.append((title, False))

    def mark_done(self, title: str) -> None:
        """Mark the last entry as done, updating its title if needed."""
        if self._window:
            self._window[-1] = (title, True)

    def __rich__(self) -> Group:
        table = Table.grid(padding=(0, 1))
        for song_title, done in self._window:
            icon = (
                Text("✓", style="bold green")
                if done
                else self._spinner.render(time.monotonic())
            )
            table.add_row(icon, song_title)
        return Group(table, self.progress)


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

    results: dict[str, dict[str, str]] = {}

    progress = Progress(
        TextColumn("[bold blue]Songs"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )
    display = _LiveDisplay(progress)
    task_id: TaskID = progress.add_task("scraping", total=len(song_links))

    with Live(display, refresh_per_second=10):
        for link_title, song_url in song_links:
            display.set_current(link_title)

            song_html = fetch_page(
                song_url, cache_dir, delay, force, _last_request_time=last_request_time
            )

            title = extract_song_title(song_html) or link_title
            pdf_urls = extract_pdf_urls(song_html, BASE_URL)
            results[title] = {"site": song_url, **pdf_urls}

            display.mark_done(title)
            progress.advance(task_id)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    typer.echo(f"Wrote {len(results)} entries to {output}")
