"""Typer CLI for the Tom Lehrer song scraper."""

from __future__ import annotations

import re
import sqlite3
import time
import zlib
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

import ollama
import typer
from httpx import ReadTimeout
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

from lehrer_lyrics.scraper.converter import pdf_to_markdown as _convert_pdf
from lehrer_lyrics.scraper.fetcher import _slug_from_url, fetch_binary, fetch_page
from lehrer_lyrics.scraper.models import SongCatalog, SongEntry
from lehrer_lyrics.scraper.parser import (
    extract_pdf_urls,
    extract_song_links,
    extract_song_title,
)

BASE_URL = "https://tomlehrersongs.com"
SONGS_URL = f"{BASE_URL}/songs/"
_WINDOW_SIZE = 10
_CLOUD_HOST = "https://ollama.com"
_DB_DEFAULT_OUTPUT = Path(__file__).parent.parent / "service" / "songs.db"


class _LyricsTask(NamedTuple):
    song_title: str
    pdf_path: Path
    md_stem: str  # filename stem for the output Markdown file (e.g. "alma")


def _slugify(text: str) -> str:
    """Convert a song title to a URL-safe slug (lowercase, hyphens, no punctuation)."""
    t = text.lower()
    t = re.sub(r"[^a-z0-9\s-]", "", t)
    t = re.sub(r"\s+", "-", t.strip())
    return re.sub(r"-{2,}", "-", t)


def _match_title_and_url(
    md_slug: str,
    slug_to_title_url: dict[str, tuple[str, str]],
) -> tuple[str | None, str | None]:
    """Return (canonical_title, site_url) for a markdown slug, or (None, None).

    Matching strategy:
    1. Exact slug match.
    2. Prefix match: the JSON slug starts with ``md_slug + "-"`` (handles verbose
       JSON titles like "The Elements (incl. …)" vs short file slug "the-elements").
    """
    if md_slug in slug_to_title_url:
        return slug_to_title_url[md_slug]
    for json_slug, (title, url) in slug_to_title_url.items():
        if json_slug.startswith(md_slug + "-"):
            return title, url
    return None, None


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

    results = SongCatalog(root={})

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
            results.root[title] = SongEntry(site=song_url, **pdf_urls)

            display.mark_done(title)
            progress.advance(task_id)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(results.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"Wrote {len(results.root)} entries to {output}")


@app.command()
def download_pdfs(
    input: Path = typer.Option(
        Path("song-urls.json"),
        help="JSON file produced by the 'scrape' command.",
    ),
    cache_dir: Path = typer.Option(
        Path(".cache/pdf"),
        help="Directory for cached PDF files.",
    ),
    delay: float = typer.Option(
        2.0,
        help="Seconds to wait between HTTP requests.",
        min=0.0,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-download PDFs even if they are already cached.",
    ),
) -> None:
    """Download all PDFs for every song listed in the scrape output JSON."""
    if not input.exists():
        typer.echo(
            f"Error: input file '{input}' not found. "
            "Run the 'scrape' command first to generate it.",
            err=True,
        )
        raise typer.Exit(code=1)

    data = SongCatalog.model_validate_json(input.read_text(encoding="utf-8"))

    # Flatten to (song_title, pdf_url) — skip the "site" field
    tasks: list[tuple[str, str]] = [
        (song_title, url)
        for song_title, entry in data.root.items()
        for url in entry.pdf_urls.values()
    ]

    if not tasks:
        typer.echo("No PDF URLs found in the input file. Nothing to do.")
        raise typer.Exit(code=0)

    last_request_time: list[float] = []

    progress = Progress(
        TextColumn("[bold blue]PDFs"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )
    display = _LiveDisplay(progress)
    task_id: TaskID = progress.add_task("downloading", total=len(tasks))

    with Live(display, refresh_per_second=10):
        for song_title, pdf_url in tasks:
            display.set_current(song_title)
            fetch_binary(
                pdf_url, cache_dir, delay, force, _last_request_time=last_request_time
            )
            display.mark_done(song_title)
            progress.advance(task_id)

    typer.echo(f"Downloaded {len(tasks)} PDF(s) to {cache_dir}")


@app.command()
def pdf_to_markdown(
    input: Path = typer.Option(
        Path("song-urls.json"),
        help="JSON file produced by the 'scrape' command.",
    ),
    pdf_cache_dir: Path = typer.Option(
        Path(".cache/pdf"),
        help="Directory containing cached PDF files.",
    ),
    output_dir: Path = typer.Option(
        Path(".cache/markdown"),
        help="Directory for output Markdown files.",
    ),
    model: str = typer.Option(
        "ministral-3:14b",
        help="Ollama model name to use for polishing lyrics.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-process PDFs even if a Markdown file already exists.",
    ),
    llm_timeout: float = typer.Option(
        60.0,
        help="Per-request timeout in seconds for the Ollama chat call.",
        min=1.0,
    ),
    llm_max_retries: int = typer.Option(
        3,
        help="Total number of LLM call attempts (first try + retries) on RequestError.",
        min=1,
    ),
    poll_interval: float = typer.Option(
        5.0,
        help="Seconds between readiness polls while waiting for Ollama to recover.",
        min=0.1,
    ),
    ready_timeout: float = typer.Option(
        120.0,
        help="Maximum seconds to wait for Ollama to become responsive after a failure.",
        min=1.0,
    ),
    cloud: bool = typer.Option(
        False,
        "--cloud",
        help="Use the Ollama cloud API instead of a local server. "
        "You will be prompted for an API key.",
    ),
) -> None:
    """Convert cached lyrics PDFs to polished Markdown using a local or cloud Ollama LLM."""
    # --- Cloud setup: prompt for API key securely ---
    ollama_host: str | None = None
    ollama_headers: dict[str, str] | None = None
    if cloud:
        api_key = typer.prompt("Ollama Cloud API key", hide_input=True)
        ollama_host = _CLOUD_HOST
        ollama_headers = {"Authorization": f"Bearer {api_key}"}

    # --- Pre-flight: input file ---
    if not input.exists():
        typer.echo(
            f"Error: input file '{input}' not found. "
            "Run the 'scrape' command first to generate it.",
            err=True,
        )
        raise typer.Exit(code=1)

    # --- Pre-flight: Ollama connectivity + model availability ---
    if cloud:
        cloud_client = ollama.Client(host=_CLOUD_HOST, headers=ollama_headers)
        try:
            available_models = sorted(
                [m.model for m in cloud_client.list().models if m.model is not None]
            )
        except ollama.RequestError as exc:
            typer.echo(
                f"Error: Ollama cloud API ({_CLOUD_HOST}) is not reachable: {exc}",
                err=True,
            )
            raise typer.Exit(code=1)
        except ollama.ResponseError as exc:
            typer.echo(
                f"Error: Ollama cloud API returned an error "
                f"(check your API key): {exc}",
                err=True,
            )
            raise typer.Exit(code=1)
    else:
        try:
            available_models = sorted(
                [m.model for m in ollama.list().models if m.model is not None]
            )
        except ollama.RequestError as exc:
            typer.echo(f"Error: Ollama server is not reachable: {exc}", err=True)
            raise typer.Exit(code=1)

    if model not in available_models:
        typer.echo(
            f"Error: model '{model}' is not available. "
            f"Available models: {', '.join(list(available_models)) or '(none)'}",
            err=True,
        )
        raise typer.Exit(code=1)

    # --- Build task list (lyrics PDFs only) ---
    data = SongCatalog.model_validate_json(input.read_text(encoding="utf-8"))
    tasks: list[_LyricsTask] = []
    for song_title, entry in data.root.items():
        for label, url in entry.pdf_urls.items():
            if "Lyrics" not in label:
                continue
            slug = _slug_from_url(url)
            pdf_path = pdf_cache_dir / slug
            md_stem = Path(urlparse(url).path).stem
            tasks.append(_LyricsTask(song_title, pdf_path, md_stem))

    if not tasks:
        typer.echo("No lyrics PDFs found in the input file. Nothing to do.")
        raise typer.Exit(code=0)

    output_dir.mkdir(parents=True, exist_ok=True)

    progress = Progress(
        TextColumn("[bold blue]Markdown"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )
    display = _LiveDisplay(progress)
    task_id: TaskID = progress.add_task("converting", total=len(tasks))

    converted = 0
    skipped = 0

    with Live(display, refresh_per_second=10):
        for task in tasks:
            display.set_current(task.song_title)

            if not task.pdf_path.exists():
                typer.echo(
                    f"Warning: PDF not found in cache: {task.pdf_path} — skipping.",
                    err=True,
                )
                progress.advance(task_id)
                skipped += 1
                continue

            md_path = output_dir / (task.md_stem + ".md")

            if md_path.exists() and not force:
                progress.advance(task_id)
                skipped += 1
                display.mark_done(task.song_title)
                continue

            if (
                task.pdf_path.name.endswith("-music.pdf")
                or task.pdf_path.name.endswith("-score.pdf")
                or task.pdf_path.name.endswith("-final.pdf")
                or task.pdf_path.name.endswith("score-p.1.pdf")
                or task.pdf_path.name.endswith("score-p.2.pdf")
                or task.pdf_path.name.endswith("-addenda.pdf")
            ):
                progress.advance(task_id)
                skipped += 1
                display.mark_done(task.song_title)
                continue

            try:
                markdown = _convert_pdf(
                    task.pdf_path,
                    model,
                    timeout=llm_timeout,
                    max_retries=llm_max_retries,
                    poll_interval=poll_interval,
                    ready_timeout=ready_timeout,
                    host=ollama_host,
                    headers=ollama_headers,
                )
            except (ollama.RequestError, ollama.ResponseError, ReadTimeout) as exc:
                typer.echo(
                    f"Warning: failed to convert '{task.song_title}': {exc} — skipping.",
                    err=True,
                )
                progress.advance(task_id)
                skipped += 1
                continue
            md_path.write_text(markdown, encoding="utf-8")
            converted += 1

            display.mark_done(task.song_title)
            progress.advance(task_id)

    typer.echo(
        f"Converted {converted} PDF(s) to Markdown in {output_dir} ({skipped} skipped)."
    )


@app.command()
def build_db(
    markdown_dir: Path = typer.Option(
        Path(".cache/markdown"),
        help="Directory containing Markdown lyrics files (output of pdf-to-markdown).",
    ),
    songs_json: Path = typer.Option(
        Path("song-urls.json"),
        help="JSON catalog from the 'scrape' command, used to attach site URLs.",
    ),
    output: Path = typer.Option(
        _DB_DEFAULT_OUTPUT,
        help="Output path for the SQLite database.",
    ),
) -> None:
    """Build the SQLite lyrics database used by the web service.

    Reads all Markdown files from MARKDOWN_DIR, matches them against the
    SONGS_JSON catalog to attach canonical titles and site URLs, compresses
    the lyrics with zlib, and writes them into a compact SQLite database at
    OUTPUT.  Run this command locally after updating the Markdown cache, then
    commit the resulting ``songs.db`` so the deployed service can use it.
    """
    if not markdown_dir.is_dir():
        typer.echo(f"Error: markdown directory not found: {markdown_dir}", err=True)
        raise typer.Exit(code=1)

    slug_to_title_url: dict[str, tuple[str, str]] = {}
    if songs_json.exists():
        catalog = SongCatalog.model_validate_json(
            songs_json.read_text(encoding="utf-8")
        )
        for title, entry in catalog.root.items():
            slug_to_title_url[_slugify(title)] = (title, entry.site)
    else:
        typer.echo(
            f"Warning: {songs_json} not found — site URLs will be NULL.", err=True
        )

    md_files = sorted(markdown_dir.glob("*.md"))
    if not md_files:
        typer.echo(f"Error: no .md files found in {markdown_dir}", err=True)
        raise typer.Exit(code=1)

    output.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(output)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS songs (
                title     TEXT NOT NULL,
                slug      TEXT PRIMARY KEY,
                site_url  TEXT,
                lyrics_gz BLOB NOT NULL
            )
            """
        )
        inserted = 0
        for md_path in md_files:
            md_slug = md_path.stem
            canonical_title, site_url = _match_title_and_url(md_slug, slug_to_title_url)
            title = canonical_title or md_slug.replace("-", " ").title()
            lyrics_gz = zlib.compress(
                md_path.read_text(encoding="utf-8").encode("utf-8"), level=9
            )
            conn.execute(
                "INSERT OR REPLACE INTO songs (title, slug, site_url, lyrics_gz)"
                " VALUES (?, ?, ?, ?)",
                (title, md_slug, site_url, lyrics_gz),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()

    typer.echo(f"Built {output} with {inserted} song(s).")
