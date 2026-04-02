"""Tests for lehrer_lyrics.scraper.fetcher (fetch_binary and fetch_page)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lehrer_lyrics.scraper.fetcher import fetch_binary, fetch_page

PDF_BYTES = b"%PDF-1.4 fake pdf content"
PDF_URL = "https://tomlehrersongs.com/wp-content/uploads/2019/03/alma.pdf"
PDF_SLUG = "wp-content_uploads_2019_03_alma.pdf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(content: bytes = PDF_BYTES) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Cache hit
# ---------------------------------------------------------------------------


def test_cache_hit_returns_cached_bytes(tmp_path: Path) -> None:
    cache_file = tmp_path / PDF_SLUG
    cache_file.write_bytes(PDF_BYTES)

    with patch("lehrer_lyrics.scraper.fetcher.httpx.get") as mock_get:
        result = fetch_binary(PDF_URL, tmp_path, delay=2.0, force=False)

    assert result == PDF_BYTES
    mock_get.assert_not_called()


def test_cache_hit_does_not_sleep(tmp_path: Path) -> None:
    (tmp_path / PDF_SLUG).write_bytes(PDF_BYTES)

    with patch("lehrer_lyrics.scraper.fetcher.time.sleep") as mock_sleep:
        fetch_binary(PDF_URL, tmp_path, delay=2.0, force=False)

    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Cache miss (live fetch)
# ---------------------------------------------------------------------------


def test_cache_miss_fetches_and_writes(tmp_path: Path) -> None:
    with patch(
        "lehrer_lyrics.scraper.fetcher.httpx.get", return_value=_make_response()
    ):
        result = fetch_binary(PDF_URL, tmp_path, delay=0.0, force=False)

    assert result == PDF_BYTES
    assert (tmp_path / PDF_SLUG).read_bytes() == PDF_BYTES


def test_cache_miss_creates_cache_dir(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    with patch(
        "lehrer_lyrics.scraper.fetcher.httpx.get", return_value=_make_response()
    ):
        fetch_binary(PDF_URL, nested, delay=0.0, force=False)

    assert nested.is_dir()
    assert (nested / PDF_SLUG).exists()


# ---------------------------------------------------------------------------
# Force re-fetch
# ---------------------------------------------------------------------------


def test_force_refetches_despite_cache(tmp_path: Path) -> None:
    cache_file = tmp_path / PDF_SLUG
    cache_file.write_bytes(b"stale")

    fresh = b"%PDF fresh"
    with patch(
        "lehrer_lyrics.scraper.fetcher.httpx.get", return_value=_make_response(fresh)
    ):
        result = fetch_binary(PDF_URL, tmp_path, delay=0.0, force=True)

    assert result == fresh
    assert cache_file.read_bytes() == fresh


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limit_sleeps_when_too_soon(tmp_path: Path) -> None:
    last = [0.0]  # simulate a request that just happened

    with (
        patch("lehrer_lyrics.scraper.fetcher.httpx.get", return_value=_make_response()),
        patch("lehrer_lyrics.scraper.fetcher.time.monotonic", return_value=0.5),
        patch("lehrer_lyrics.scraper.fetcher.time.sleep") as mock_sleep,
    ):
        fetch_binary(PDF_URL, tmp_path, delay=2.0, force=False, _last_request_time=last)

    mock_sleep.assert_called_once_with(pytest.approx(1.5, abs=1e-6))


def test_rate_limit_no_sleep_when_enough_time_has_passed(tmp_path: Path) -> None:
    last = [0.0]  # simulate a request long ago

    with (
        patch("lehrer_lyrics.scraper.fetcher.httpx.get", return_value=_make_response()),
        patch("lehrer_lyrics.scraper.fetcher.time.monotonic", return_value=5.0),
        patch("lehrer_lyrics.scraper.fetcher.time.sleep") as mock_sleep,
    ):
        fetch_binary(PDF_URL, tmp_path, delay=2.0, force=False, _last_request_time=last)

    mock_sleep.assert_not_called()


def test_last_request_time_updated_after_fetch(tmp_path: Path) -> None:
    last: list[float] = []

    with (
        patch("lehrer_lyrics.scraper.fetcher.httpx.get", return_value=_make_response()),
        patch("lehrer_lyrics.scraper.fetcher.time.monotonic", return_value=42.0),
    ):
        fetch_binary(PDF_URL, tmp_path, delay=2.0, force=False, _last_request_time=last)

    assert last == [42.0]


# ---------------------------------------------------------------------------
# fetch_page
# ---------------------------------------------------------------------------

HTML_URL = "https://tomlehrersongs.com/songs/"
HTML_SLUG = "songs"
HTML_CONTENT = "<html><body>Hello</body></html>"


def _make_html_response(text: str = HTML_CONTENT) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


class TestFetchPage:
    def test_cache_hit_returns_cached_html(self, tmp_path: Path) -> None:
        cache_file = tmp_path / f"{HTML_SLUG}.html"
        cache_file.write_text(HTML_CONTENT, encoding="utf-8")

        with patch("lehrer_lyrics.scraper.fetcher.httpx.get") as mock_get:
            result = fetch_page(HTML_URL, tmp_path, delay=2.0, force=False)

        assert result == HTML_CONTENT
        mock_get.assert_not_called()

    def test_cache_hit_does_not_sleep(self, tmp_path: Path) -> None:
        (tmp_path / f"{HTML_SLUG}.html").write_text(HTML_CONTENT, encoding="utf-8")

        with patch("lehrer_lyrics.scraper.fetcher.time.sleep") as mock_sleep:
            fetch_page(HTML_URL, tmp_path, delay=2.0, force=False)

        mock_sleep.assert_not_called()

    def test_cache_miss_fetches_and_writes(self, tmp_path: Path) -> None:
        with patch(
            "lehrer_lyrics.scraper.fetcher.httpx.get",
            return_value=_make_html_response(),
        ):
            result = fetch_page(HTML_URL, tmp_path, delay=0.0, force=False)

        assert result == HTML_CONTENT
        assert (tmp_path / f"{HTML_SLUG}.html").read_text(
            encoding="utf-8"
        ) == HTML_CONTENT

    def test_cache_miss_creates_cache_dir(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b"
        with patch(
            "lehrer_lyrics.scraper.fetcher.httpx.get",
            return_value=_make_html_response(),
        ):
            fetch_page(HTML_URL, nested, delay=0.0, force=False)

        assert nested.is_dir()
        assert (nested / f"{HTML_SLUG}.html").exists()

    def test_force_refetches_despite_cache(self, tmp_path: Path) -> None:
        cache_file = tmp_path / f"{HTML_SLUG}.html"
        cache_file.write_text("<html>stale</html>", encoding="utf-8")

        fresh = "<html>fresh</html>"
        with patch(
            "lehrer_lyrics.scraper.fetcher.httpx.get",
            return_value=_make_html_response(fresh),
        ):
            result = fetch_page(HTML_URL, tmp_path, delay=0.0, force=True)

        assert result == fresh
        assert cache_file.read_text(encoding="utf-8") == fresh

    def test_rate_limit_sleeps_when_too_soon(self, tmp_path: Path) -> None:
        last = [0.0]

        with (
            patch(
                "lehrer_lyrics.scraper.fetcher.httpx.get",
                return_value=_make_html_response(),
            ),
            patch("lehrer_lyrics.scraper.fetcher.time.monotonic", return_value=0.5),
            patch("lehrer_lyrics.scraper.fetcher.time.sleep") as mock_sleep,
        ):
            fetch_page(
                HTML_URL, tmp_path, delay=2.0, force=False, _last_request_time=last
            )

        mock_sleep.assert_called_once_with(pytest.approx(1.5, abs=1e-6))

    def test_rate_limit_no_sleep_when_enough_time_passed(self, tmp_path: Path) -> None:
        last = [0.0]

        with (
            patch(
                "lehrer_lyrics.scraper.fetcher.httpx.get",
                return_value=_make_html_response(),
            ),
            patch("lehrer_lyrics.scraper.fetcher.time.monotonic", return_value=5.0),
            patch("lehrer_lyrics.scraper.fetcher.time.sleep") as mock_sleep,
        ):
            fetch_page(
                HTML_URL, tmp_path, delay=2.0, force=False, _last_request_time=last
            )

        mock_sleep.assert_not_called()

    def test_last_request_time_updated_after_fetch(self, tmp_path: Path) -> None:
        last: list[float] = []

        with (
            patch(
                "lehrer_lyrics.scraper.fetcher.httpx.get",
                return_value=_make_html_response(),
            ),
            patch("lehrer_lyrics.scraper.fetcher.time.monotonic", return_value=99.0),
        ):
            fetch_page(
                HTML_URL, tmp_path, delay=0.0, force=False, _last_request_time=last
            )

        assert last == [99.0]

    def test_last_request_time_updated_when_already_set(self, tmp_path: Path) -> None:
        last: list[float] = [1.0]

        with (
            patch(
                "lehrer_lyrics.scraper.fetcher.httpx.get",
                return_value=_make_html_response(),
            ),
            patch("lehrer_lyrics.scraper.fetcher.time.monotonic", return_value=10.0),
        ):
            fetch_page(
                HTML_URL, tmp_path, delay=0.0, force=False, _last_request_time=last
            )

        assert last == [10.0]
