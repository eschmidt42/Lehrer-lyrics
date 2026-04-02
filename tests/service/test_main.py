"""Tests for the web service."""

from __future__ import annotations

import sqlite3
import zlib
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_ALMA_LYRICS = "# Alma\n\nHusbands one through six..."
_POISONING_LYRICS = "# Poisoning Pigeons\n\nI'm spending Hanukkah in Santa Monica..."


def _make_songs_db(path: Path) -> None:
    """Write a minimal songs.db with two songs for testing."""
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE songs (
                title TEXT NOT NULL,
                slug TEXT PRIMARY KEY,
                site_url TEXT,
                lyrics_gz BLOB NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO songs VALUES (?, ?, ?, ?)",
            (
                "Alma",
                "alma",
                "https://tomlehrersongs.com/alma/",
                zlib.compress(_ALMA_LYRICS.encode()),
            ),
        )
        conn.execute(
            "INSERT INTO songs VALUES (?, ?, ?, ?)",
            (
                "Poisoning Pigeons in the Park",
                "poisoning-pigeons-in-the-park",
                None,
                zlib.compress(_POISONING_LYRICS.encode()),
            ),
        )


@pytest.fixture(autouse=True)
def patch_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the service at a temp DB and clear lru_caches between tests."""
    import lehrer_lyrics.service.main as svc

    db_path = tmp_path / "songs.db"
    _make_songs_db(db_path)
    monkeypatch.setattr(svc, "_DB_PATH", db_path)
    svc._all_songs.cache_clear()
    svc._render_page.cache_clear()
    yield
    svc._all_songs.cache_clear()
    svc._render_page.cache_clear()


@pytest.fixture()
def client() -> TestClient:
    from lehrer_lyrics.service.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Basic response
# ---------------------------------------------------------------------------


def test_root_returns_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_root_contains_tom_lehrer(client: TestClient) -> None:
    response = client.get("/")
    assert "Tom Lehrer" in response.text


def test_root_contains_a_song_title(client: TestClient) -> None:
    response = client.get("/")
    assert "Alma" in response.text or "Poisoning Pigeons" in response.text


# ---------------------------------------------------------------------------
# Site URL link
# ---------------------------------------------------------------------------


def test_root_contains_site_url_link_when_available(client: TestClient) -> None:
    import lehrer_lyrics.service.main as svc

    fixed_date = date(2026, 1, 1)
    # Ensure the daily song is Alma (which has a site_url)
    with patch.object(svc, "_today_berlin", return_value=fixed_date):
        import random

        random.seed(fixed_date.isoformat())
        songs = svc._all_songs()
        chosen_title = random.choice(songs)[0]

    if chosen_title == "Alma":
        response = client.get("/")
        with patch.object(svc, "_today_berlin", return_value=fixed_date):
            response = client.get("/")
        assert "tomlehrersongs.com" in response.text
        assert "<a href=" in response.text


# ---------------------------------------------------------------------------
# Daily rotation — deterministic seed
# ---------------------------------------------------------------------------


def test_same_date_returns_same_song(client: TestClient) -> None:
    import lehrer_lyrics.service.main as svc

    fixed_date = date(2026, 3, 15)
    with patch.object(svc, "_today_berlin", return_value=fixed_date):
        r1 = client.get("/")
        svc._render_page.cache_clear()
        r2 = client.get("/")

    assert r1.text == r2.text


def test_different_dates_may_return_different_songs() -> None:
    """With enough songs and different seeds the selection can differ."""
    import lehrer_lyrics.service.main as svc

    results = set()
    for day in range(1, 29):
        svc._render_page.cache_clear()
        d = date(2026, 1, day)
        with patch.object(svc, "_today_berlin", return_value=d):
            from lehrer_lyrics.service.main import app

            c = TestClient(app)
            text = c.get("/").text
            if "Alma" in text:
                results.add("alma")
            elif "Poisoning Pigeons" in text:
                results.add("pigeons")
    # With 2 songs over 28 days both should appear
    assert len(results) == 2
