"""Tests for the build-db CLI command."""

from __future__ import annotations

import json
import sqlite3
import zlib
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lehrer_lyrics.scraper.cli import _match_title_and_url, _slugify, app

runner = CliRunner()

_SONGS_JSON = {
    "Alma": {"site": "https://tomlehrersongs.com/alma/"},
    "The Elements (incl. the Aristotle version)": {
        "site": "https://tomlehrersongs.com/the-elements/"
    },
    "Be Prepared": {"site": "https://tomlehrersongs.com/be-prepared/"},
}

_ALMA_LYRICS = "# Alma\n\nHusbands one through six..."
_ELEMENTS_LYRICS = "# The Elements\n\nThere's antimony, arsenic..."
_BE_PREPARED_LYRICS = "# Be Prepared\n\nBe prepared!"
_UNKNOWN_LYRICS = "# Mystery Song\n\nNo URL for this one."


@pytest.fixture()
def markdown_dir(tmp_path: Path) -> Path:
    md = tmp_path / "markdown"
    md.mkdir()
    (md / "alma.md").write_text(_ALMA_LYRICS, encoding="utf-8")
    (md / "the-elements.md").write_text(_ELEMENTS_LYRICS, encoding="utf-8")
    (md / "be-prepared.md").write_text(_BE_PREPARED_LYRICS, encoding="utf-8")
    (md / "unknown-song.md").write_text(_UNKNOWN_LYRICS, encoding="utf-8")
    return md


@pytest.fixture()
def songs_json(tmp_path: Path) -> Path:
    p = tmp_path / "song-urls.json"
    p.write_text(json.dumps(_SONGS_JSON), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _slugify helper
# ---------------------------------------------------------------------------


def test_slugify_basic() -> None:
    assert _slugify("Alma") == "alma"


def test_slugify_spaces_become_hyphens() -> None:
    assert _slugify("A Christmas Carol") == "a-christmas-carol"


def test_slugify_strips_punctuation() -> None:
    assert _slugify("Are There Any Questions?") == "are-there-any-questions"


def test_slugify_strips_parentheses() -> None:
    assert _slugify("The Elements (incl. the Aristotle version)") == (
        "the-elements-incl-the-aristotle-version"
    )


# ---------------------------------------------------------------------------
# _match_title_and_url helper
# ---------------------------------------------------------------------------


def test_match_exact() -> None:
    mapping = {"alma": ("Alma", "https://tomlehrersongs.com/alma/")}
    title, url = _match_title_and_url("alma", mapping)
    assert title == "Alma"
    assert url == "https://tomlehrersongs.com/alma/"


def test_match_prefix() -> None:
    mapping = {
        "the-elements-incl-the-aristotle-version": (
            "The Elements (incl. the Aristotle version)",
            "https://tomlehrersongs.com/the-elements/",
        )
    }
    title, url = _match_title_and_url("the-elements", mapping)
    assert title == "The Elements (incl. the Aristotle version)"
    assert url == "https://tomlehrersongs.com/the-elements/"


def test_match_no_match_returns_none() -> None:
    title, url = _match_title_and_url("completely-unknown", {})
    assert title is None
    assert url is None


# ---------------------------------------------------------------------------
# build-db command: happy path
# ---------------------------------------------------------------------------


def test_build_db_creates_database(
    tmp_path: Path, markdown_dir: Path, songs_json: Path
) -> None:
    output = tmp_path / "songs.db"
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(markdown_dir),
            "--songs-json",
            str(songs_json),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.exists()


def test_build_db_output_message(
    tmp_path: Path, markdown_dir: Path, songs_json: Path
) -> None:
    output = tmp_path / "songs.db"
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(markdown_dir),
            "--songs-json",
            str(songs_json),
            "--output",
            str(output),
        ],
    )

    assert "4 song(s)" in result.output


def test_build_db_song_count(
    tmp_path: Path, markdown_dir: Path, songs_json: Path
) -> None:
    output = tmp_path / "songs.db"
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(markdown_dir),
            "--songs-json",
            str(songs_json),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output

    with closing(sqlite3.connect(output)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    assert count == 4


def test_build_db_site_url_attached(
    tmp_path: Path, markdown_dir: Path, songs_json: Path
) -> None:
    output = tmp_path / "songs.db"
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(markdown_dir),
            "--songs-json",
            str(songs_json),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output

    with closing(sqlite3.connect(output)) as conn:
        row = conn.execute("SELECT site_url FROM songs WHERE slug = 'alma'").fetchone()
    assert row is not None
    assert row[0] == "https://tomlehrersongs.com/alma/"


def test_build_db_prefix_match_attaches_url(
    tmp_path: Path, markdown_dir: Path, songs_json: Path
) -> None:
    """'the-elements.md' should match the verbose JSON title via prefix matching."""
    output = tmp_path / "songs.db"
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(markdown_dir),
            "--songs-json",
            str(songs_json),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output

    with closing(sqlite3.connect(output)) as conn:
        row = conn.execute(
            "SELECT site_url FROM songs WHERE slug = 'the-elements'"
        ).fetchone()
    assert row is not None
    assert row[0] == "https://tomlehrersongs.com/the-elements/"


def test_build_db_unmatched_song_has_null_url(
    tmp_path: Path, markdown_dir: Path, songs_json: Path
) -> None:
    output = tmp_path / "songs.db"
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(markdown_dir),
            "--songs-json",
            str(songs_json),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output

    with closing(sqlite3.connect(output)) as conn:
        row = conn.execute(
            "SELECT site_url FROM songs WHERE slug = 'unknown-song'"
        ).fetchone()
    assert row is not None
    assert row[0] is None


def test_build_db_lyrics_stored_compressed(
    tmp_path: Path, markdown_dir: Path, songs_json: Path
) -> None:
    output = tmp_path / "songs.db"
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(markdown_dir),
            "--songs-json",
            str(songs_json),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output

    with closing(sqlite3.connect(output)) as conn:
        row = conn.execute("SELECT lyrics_gz FROM songs WHERE slug = 'alma'").fetchone()
    assert row is not None
    decompressed = zlib.decompress(row[0]).decode("utf-8")
    assert decompressed == _ALMA_LYRICS


def test_build_db_is_idempotent(
    tmp_path: Path, markdown_dir: Path, songs_json: Path
) -> None:
    """Running build-db twice rebuilds from scratch and yields the same row count."""
    output = tmp_path / "songs.db"
    args = [
        "build-db",
        "--markdown-dir",
        str(markdown_dir),
        "--songs-json",
        str(songs_json),
        "--output",
        str(output),
    ]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    with closing(sqlite3.connect(output)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    assert count == 4


def test_build_db_creates_parent_dirs(
    tmp_path: Path, markdown_dir: Path, songs_json: Path
) -> None:
    output = tmp_path / "nested" / "deep" / "songs.db"
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(markdown_dir),
            "--songs-json",
            str(songs_json),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert output.exists()


def test_build_db_unmatched_song_title_derived_from_slug(
    tmp_path: Path, markdown_dir: Path, songs_json: Path
) -> None:
    output = tmp_path / "songs.db"
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(markdown_dir),
            "--songs-json",
            str(songs_json),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output

    with closing(sqlite3.connect(output)) as conn:
        row = conn.execute(
            "SELECT title FROM songs WHERE slug = 'unknown-song'"
        ).fetchone()
    assert row is not None
    assert row[0] == "Unknown Song"


# ---------------------------------------------------------------------------
# build-db command: error cases
# ---------------------------------------------------------------------------


def test_build_db_missing_markdown_dir_exits(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(tmp_path / "nonexistent"),
            "--output",
            str(tmp_path / "songs.db"),
        ],
    )

    assert result.exit_code == 1
    assert "not found" in result.output


def test_build_db_empty_markdown_dir_exits(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(empty_dir),
            "--output",
            str(tmp_path / "songs.db"),
        ],
    )

    assert result.exit_code == 1
    assert "no .md files" in result.output


def test_build_db_missing_songs_json_warns(tmp_path: Path, markdown_dir: Path) -> None:
    result = runner.invoke(
        app,
        [
            "build-db",
            "--markdown-dir",
            str(markdown_dir),
            "--songs-json",
            str(tmp_path / "nonexistent.json"),
            "--output",
            str(tmp_path / "songs.db"),
        ],
    )

    assert result.exit_code == 0
    assert "Warning" in result.output
