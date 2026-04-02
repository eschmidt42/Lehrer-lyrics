"""HTML parsing for the Tom Lehrer song scraper."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def _clean_label(text: str) -> str:
    """Strip special characters from a pre-link label.

    Removes leading/trailing whitespace, trailing colons, and collapses
    internal whitespace to a single space.
    """
    text = text.strip().rstrip(":").strip()
    return re.sub(r"\s+", " ", text)


def extract_song_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Extract song links from the main songs listing page.

    Looks inside ``<main id="main"> → <section id="content">`` for anchor
    tags whose href looks like a song slug (i.e. a relative path).

    Args:
        html: Raw HTML of the main songs page.
        base_url: Base URL to resolve relative hrefs (e.g. ``https://tomlehrersongs.com``).

    Returns:
        List of ``(title, absolute_url)`` tuples, one per song link.
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main", id="main")
    if main is None:
        return []
    section = main.find("section", id="content")
    if section is None:
        return []

    links: list[tuple[str, str]] = []
    for a in section.find_all("a", href=True):
        href = str(a["href"])
        # Skip external links and anchors; only keep relative song-slug paths
        if href.startswith("#") or href.startswith("http"):
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        links.append((title, urljoin(base_url, href)))
    return links


def extract_pdf_urls(html: str, base_url: str) -> dict[str, str]:
    """Extract PDF links from an individual song page.

    Looks inside ``<main id="main"> → <section id="content">`` for anchor
    tags whose ``href`` ends with ``.pdf``. The key for each URL is the
    text node immediately preceding the anchor within its parent element,
    cleaned of special characters.

    Args:
        html: Raw HTML of a song page.
        base_url: Base URL to resolve relative PDF hrefs.

    Returns:
        Dict mapping cleaned label text to absolute PDF URL.  An empty dict
        is returned when no PDF links are found.
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main", id="main")
    if main is None:
        return {}
    section = main.find("section", id="content")
    if section is None:
        return {}

    result: dict[str, str] = {}
    for a in section.find_all("a", href=True):
        href = str(a["href"])
        if not href.lower().endswith(".pdf"):
            continue

        # Collect preceding text nodes within the same parent element.
        # In BeautifulSoup every sibling is either a Tag or NavigableString,
        # both of which expose get_text().
        label_parts: list[str] = []
        for sibling in a.previous_siblings:
            if hasattr(sibling, "get_text"):
                label_parts.append(sibling.get_text())

        raw_label = "".join(reversed(label_parts))
        label = _clean_label(raw_label)
        if not label:
            label = _clean_label(a.get_text())

        result[label] = urljoin(base_url, href)
    return result


def extract_song_title(html: str) -> str | None:
    """Extract the song title from an individual song page.

    Tries ``<h1 class="entry-title">`` first, then falls back to
    ``<span class="entry-title">``.

    Args:
        html: Raw HTML of a song page.

    Returns:
        Title string, or ``None`` if not found.
    """
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1", class_="entry-title")
    if h1:
        return h1.get_text(strip=True)
    span = soup.find("span", class_="entry-title")
    if span:
        return span.get_text(strip=True)
    return None
