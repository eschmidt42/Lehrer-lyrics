"""Tests for the scrape CLI command and the _LiveDisplay helper class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from lehrer_lyrics.scraper.cli import _WINDOW_SIZE, _LiveDisplay, app

runner = CliRunner()

MAIN_HTML = """\
<html><body>
<main id="main">
  <section id="content">
    <a href="/alma/">Alma</a>
    <a href="/poisoning-pigeons/">Poisoning Pigeons</a>
  </section>
</main>
</body></html>
"""

SONG_HTML = """\
<html><body>
<h1 class="entry-title">{title}</h1>
<main id="main">
  <section id="content">
    <p>Lyrics: <a href="/wp-content/uploads/{slug}.pdf">view PDF</a></p>
  </section>
</main>
</body></html>
"""

ALMA_HTML = SONG_HTML.format(title="Alma", slug="alma")
PIGEONS_HTML = SONG_HTML.format(title="Poisoning Pigeons in the Park", slug="pigeons")

BASE_URL = "https://tomlehrersongs.com"


# ---------------------------------------------------------------------------
# scrape command — no song links found
# ---------------------------------------------------------------------------


def test_scrape_no_links_exits_with_error(tmp_path: Path) -> None:
    empty_html = "<html><body><main id='main'><section id='content'></section></main></body></html>"

    with patch(
        "lehrer_lyrics.scraper.cli.fetch_page",
        return_value=empty_html,
    ):
        result = runner.invoke(
            app,
            [
                "scrape",
                "--cache-dir",
                str(tmp_path / "html"),
                "--output",
                str(tmp_path / "out.json"),
            ],
        )

    assert result.exit_code == 1
    assert "No song links" in result.output


# ---------------------------------------------------------------------------
# scrape command — happy path
# ---------------------------------------------------------------------------


def test_scrape_writes_json_output(tmp_path: Path) -> None:
    html_map = {
        "https://tomlehrersongs.com/songs/": MAIN_HTML,
        f"{BASE_URL}/alma/": ALMA_HTML,
        f"{BASE_URL}/poisoning-pigeons/": PIGEONS_HTML,
    }

    def fake_fetch_page(url, cache_dir, delay, force, *, _last_request_time=None):
        return html_map[url]

    output = tmp_path / "out.json"

    with patch("lehrer_lyrics.scraper.cli.fetch_page", side_effect=fake_fetch_page):
        result = runner.invoke(
            app,
            [
                "scrape",
                "--cache-dir",
                str(tmp_path / "html"),
                "--output",
                str(output),
                "--delay",
                "0",
            ],
        )

    assert result.exit_code == 0, result.output
    assert output.exists()
    import json

    data = json.loads(output.read_text())
    assert "Alma" in data or any("alma" in k.lower() for k in data)
    assert "2 entries" in result.output


# ---------------------------------------------------------------------------
# _LiveDisplay — window overflow evicts oldest entry
# ---------------------------------------------------------------------------


def test_live_display_set_current_evicts_oldest_when_window_full() -> None:
    from rich.progress import Progress

    progress = Progress()
    display = _LiveDisplay(progress)

    for i in range(_WINDOW_SIZE):
        display.set_current(f"Song {i}")

    assert len(display._window) == _WINDOW_SIZE

    # Adding one more must evict the oldest entry (Song 0)
    display.set_current("Overflow Song")

    assert len(display._window) == _WINDOW_SIZE
    titles = [t for t, _ in display._window]
    assert "Song 0" not in titles
    assert "Overflow Song" in titles


# ---------------------------------------------------------------------------
# _LiveDisplay — mark_done on an empty window is a no-op
# ---------------------------------------------------------------------------


def test_live_display_mark_done_on_empty_window_is_noop() -> None:
    from rich.progress import Progress

    progress = Progress()
    display = _LiveDisplay(progress)

    # Should not raise even though the window is empty
    display.mark_done("Ghost Song")
    assert display._window == []
