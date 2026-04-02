"""Rate-limited, caching HTTP fetcher for the Tom Lehrer scraper."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

USER_AGENT = "lehrer-lyrics-scraper/0.1 (scraper bot; be nice)"


def _slug_from_url(url: str) -> str:
    """Derive a filesystem-safe slug from a URL path."""
    path = urlparse(url).path.strip("/")
    return path.replace("/", "_") or "index"


def fetch_page(
    url: str,
    cache_dir: Path,
    delay: float,
    force: bool,
    *,
    _last_request_time: list[float] | None = None,
) -> str:
    """Fetch a page, using disk cache when available.

    Args:
        url: Page URL to fetch.
        cache_dir: Directory for cached HTML files.
        delay: Minimum seconds between live HTTP requests.
        force: When True, ignore existing cache and re-fetch.
        _last_request_time: Single-element list used to track the last request
            timestamp across calls (pass the same list on every call).

    Returns:
        Raw HTML content of the page.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug_from_url(url)
    cache_file = cache_dir / f"{slug}.html"

    if not force and cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    # Enforce rate limit between live requests
    if _last_request_time is not None and _last_request_time:
        elapsed = time.monotonic() - _last_request_time[0]
        if elapsed < delay:
            time.sleep(delay - elapsed)

    response = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    response.raise_for_status()
    html = response.text

    if _last_request_time is not None:
        if _last_request_time:
            _last_request_time[0] = time.monotonic()
        else:
            _last_request_time.append(time.monotonic())

    cache_file.write_text(html, encoding="utf-8")
    return html
