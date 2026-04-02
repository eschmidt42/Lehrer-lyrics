"""Smoke tests for the download-pdfs CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from lehrer_lyrics.scraper.cli import app

runner = CliRunner()

SONG_DATA = {
    "Alma": {
        "site": "https://tomlehrersongs.com/alma/",
        "Lyrics": "https://tomlehrersongs.com/wp-content/uploads/2018/11/alma.pdf",
        "Sheet music": "https://tomlehrersongs.com/wp-content/uploads/2019/03/alma-music.pdf",
    },
    "Poisoning Pigeons": {
        "site": "https://tomlehrersongs.com/poisoning-pigeons-in-the-park/",
        "Lyrics": "https://tomlehrersongs.com/wp-content/uploads/2018/11/pigeons.pdf",
    },
}


# ---------------------------------------------------------------------------
# Missing input file
# ---------------------------------------------------------------------------


def test_missing_input_exits_with_error(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["download-pdfs", "--input", str(tmp_path / "nonexistent.json")],
    )

    assert result.exit_code == 1
    assert "not found" in result.output
    assert "scrape" in result.output  # hints at the fix


# ---------------------------------------------------------------------------
# Successful download
# ---------------------------------------------------------------------------


def test_downloads_all_pdfs(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps(SONG_DATA), encoding="utf-8")
    cache_dir = tmp_path / "pdf"

    fake_pdf = b"%PDF-1.4 fake"
    fetched: list[str] = []

    def fake_fetch_binary(url, *args, **kwargs):
        fetched.append(url)
        return fake_pdf

    with patch("lehrer_lyrics.scraper.cli.fetch_binary", side_effect=fake_fetch_binary):
        result = runner.invoke(
            app,
            [
                "download-pdfs",
                "--input",
                str(input_file),
                "--cache-dir",
                str(cache_dir),
            ],
        )

    assert result.exit_code == 0
    # 3 PDFs total (2 for Alma, 1 for Pigeons)
    assert len(fetched) == 3
    assert "3 PDF(s)" in result.output


def test_output_reports_cache_dir(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps(SONG_DATA), encoding="utf-8")
    cache_dir = tmp_path / "my-pdfs"

    with patch("lehrer_lyrics.scraper.cli.fetch_binary", return_value=b"%PDF"):
        result = runner.invoke(
            app,
            [
                "download-pdfs",
                "--input",
                str(input_file),
                "--cache-dir",
                str(cache_dir),
            ],
        )

    assert str(cache_dir) in result.output


# ---------------------------------------------------------------------------
# Force flag is forwarded
# ---------------------------------------------------------------------------


def test_force_flag_passed_to_fetch_binary(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(
        json.dumps(
            {"Song": {"site": "https://x.com/s/", "Lyrics": "https://x.com/s/song.pdf"}}
        ),
        encoding="utf-8",
    )

    calls: list[dict] = []

    def recording_fetch(url, cache_dir, delay, force, *, _last_request_time=None):
        calls.append({"url": url, "force": force})
        return b"%PDF"

    with patch("lehrer_lyrics.scraper.cli.fetch_binary", side_effect=recording_fetch):
        runner.invoke(
            app,
            ["download-pdfs", "--input", str(input_file), "--force"],
        )

    assert all(c["force"] for c in calls)


# ---------------------------------------------------------------------------
# Empty JSON (no PDFs)
# ---------------------------------------------------------------------------


def test_empty_pdf_list_exits_cleanly(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(
        json.dumps({"Song": {"site": "https://tomlehrersongs.com/s/"}}),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["download-pdfs", "--input", str(input_file)])

    assert result.exit_code == 0
    assert "Nothing to do" in result.output
