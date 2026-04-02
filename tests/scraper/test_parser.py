"""Tests for lehrer_lyrics.scraper.parser."""

from __future__ import annotations

from lehrer_lyrics.scraper.parser import (
    extract_pdf_urls,
    extract_song_links,
    extract_song_title,
)

# ---------------------------------------------------------------------------
# Minimal HTML fixtures
# ---------------------------------------------------------------------------

MAIN_PAGE_HTML = """\
<html><body>
<main id="main">
  <section id="content">
    <a href="/all-is-well/">All is Well</a>
    <a href="/poisoning-pigeons-in-the-park/">Poisoning Pigeons in the Park</a>
    <a href="https://external.example.com/other">External link</a>
    <a href="#anchor">Anchor link</a>
  </section>
</main>
</body></html>
"""

SONG_PAGE_HTML = """\
<html><body>
<div class="avada-page-titlebar-wrapper">
  <h1 class="entry-title">All is Well</h1>
</div>
<main id="main">
  <section id="content">
    <p>Lyrics: <a href="/wp-content/uploads/2019/03/all-is-well.pdf">view or download PDF</a></p>
  </section>
</main>
</body></html>
"""

SONG_PAGE_MULTI_PDF_HTML = """\
<html><body>
<main id="main">
  <section id="content">
    <p>Lyrics: <a href="/wp-content/uploads/song-a.pdf">view PDF</a></p>
    <p>Revised version: <a href="/wp-content/uploads/song-a-revised.pdf">view PDF</a></p>
  </section>
</main>
</body></html>
"""

SONG_PAGE_NO_MAIN_HTML = """\
<html><body>
  <p>Lyrics: <a href="/wp-content/uploads/song.pdf">view PDF</a></p>
</body></html>
"""

SONG_PAGE_SPAN_TITLE_HTML = """\
<html><body>
<main id="main">
  <section id="content">
    <span class="entry-title" style="display:none;">Hidden Title</span>
  </section>
</main>
</body></html>
"""

BASE = "https://tomlehrersongs.com"


# ---------------------------------------------------------------------------
# extract_song_links
# ---------------------------------------------------------------------------


class TestExtractSongLinks:
    def test_returns_relative_links_as_absolute(self):
        links = extract_song_links(MAIN_PAGE_HTML, BASE)
        urls = [url for _, url in links]
        assert f"{BASE}/all-is-well/" in urls
        assert f"{BASE}/poisoning-pigeons-in-the-park/" in urls

    def test_excludes_external_links(self):
        links = extract_song_links(MAIN_PAGE_HTML, BASE)
        urls = [url for _, url in links]
        assert not any("external.example.com" in u for u in urls)

    def test_excludes_anchor_links(self):
        links = extract_song_links(MAIN_PAGE_HTML, BASE)
        urls = [url for _, url in links]
        assert not any(u.startswith("#") for u in urls)

    def test_title_matches_link_text(self):
        links = extract_song_links(MAIN_PAGE_HTML, BASE)
        titles = [t for t, _ in links]
        assert "All is Well" in titles

    def test_missing_main_returns_empty(self):
        html = "<html><body><section id='content'><a href='/x/'>X</a></section></body></html>"
        assert extract_song_links(html, BASE) == []

    def test_missing_section_returns_empty(self):
        html = "<html><body><main id='main'><a href='/x/'>X</a></main></body></html>"
        assert extract_song_links(html, BASE) == []


# ---------------------------------------------------------------------------
# extract_pdf_urls
# ---------------------------------------------------------------------------


class TestExtractPdfUrls:
    def test_extracts_single_pdf(self):
        result = extract_pdf_urls(SONG_PAGE_HTML, BASE)
        assert "Lyrics" in result
        assert result["Lyrics"] == f"{BASE}/wp-content/uploads/2019/03/all-is-well.pdf"

    def test_extracts_multiple_pdfs(self):
        result = extract_pdf_urls(SONG_PAGE_MULTI_PDF_HTML, BASE)
        assert "Lyrics" in result
        assert "Revised version" in result
        assert result["Lyrics"] == f"{BASE}/wp-content/uploads/song-a.pdf"
        assert (
            result["Revised version"] == f"{BASE}/wp-content/uploads/song-a-revised.pdf"
        )

    def test_no_pdf_returns_empty(self):
        html = "<html><body><main id='main'><section id='content'><p>No PDFs here.</p></section></main></body></html>"
        assert extract_pdf_urls(html, BASE) == {}

    def test_missing_main_returns_empty(self):
        assert extract_pdf_urls(SONG_PAGE_NO_MAIN_HTML, BASE) == {}

    def test_label_strips_colon_and_whitespace(self):
        result = extract_pdf_urls(SONG_PAGE_HTML, BASE)
        assert "Lyrics" in result
        assert "Lyrics:" not in result

    def test_url_is_absolute(self):
        result = extract_pdf_urls(SONG_PAGE_HTML, BASE)
        for url in result.values():
            assert url.startswith("https://")


# ---------------------------------------------------------------------------
# extract_song_title
# ---------------------------------------------------------------------------


class TestExtractSongTitle:
    def test_extracts_h1_title(self):
        assert extract_song_title(SONG_PAGE_HTML) == "All is Well"

    def test_falls_back_to_span(self):
        assert extract_song_title(SONG_PAGE_SPAN_TITLE_HTML) == "Hidden Title"

    def test_returns_none_when_not_found(self):
        assert extract_song_title("<html><body></body></html>") is None


# Additional edge-case fixtures
SONG_PAGE_NO_SECTION_HTML = """\
<html><body>
<main id="main">
  <p>No section tag here.</p>
</main>
</body></html>
"""

# Anchor with no preceding text siblings — fallback to anchor's own text
SONG_PAGE_ANCHOR_LABEL_HTML = """\
<html><body>
<main id="main">
  <section id="content">
    <a href="/wp-content/uploads/song-b.pdf">Download Lyrics PDF</a>
  </section>
</main>
</body></html>
"""

# Raw text node immediately before the anchor (not wrapped in a tag)
SONG_PAGE_RAW_TEXT_SIBLING_HTML = """\
<html><body>
<main id="main">
  <section id="content">
    Sheet Music: <a href="/wp-content/uploads/song-c.pdf">view PDF</a>
  </section>
</main>
</body></html>
"""

# Link with no text content — should be skipped
MAIN_PAGE_EMPTY_TITLE_HTML = """\
<html><body>
<main id="main">
  <section id="content">
    <a href="/real-song/">Real Song</a>
    <a href="/empty-title/"></a>
  </section>
</main>
</body></html>
"""

# Anchor link that does NOT end in .pdf — should be skipped
SONG_PAGE_NON_PDF_LINK_HTML = """\
<html><body>
<main id="main">
  <section id="content">
    <p>Listen: <a href="/stream/song.mp3">stream here</a></p>
    <p>Lyrics: <a href="/wp-content/uploads/real.pdf">view PDF</a></p>
  </section>
</main>
</body></html>
"""


class TestExtractSongLinksEdgeCases:
    def test_skips_links_with_empty_title(self):
        links = extract_song_links(MAIN_PAGE_EMPTY_TITLE_HTML, BASE)
        titles = [t for t, _ in links]
        assert "Real Song" in titles
        # The empty-title anchor must not produce an entry
        assert all(t for t in titles)


class TestExtractPdfUrlsEdgeCases:
    def test_missing_section_returns_empty(self):
        assert extract_pdf_urls(SONG_PAGE_NO_SECTION_HTML, BASE) == {}

    def test_skips_non_pdf_links(self):
        result = extract_pdf_urls(SONG_PAGE_NON_PDF_LINK_HTML, BASE)
        # Only the .pdf link should appear; the .mp3 link must be excluded
        assert len(result) == 1
        assert all(url.endswith(".pdf") for url in result.values())

    def test_raw_text_sibling_used_as_label(self):
        result = extract_pdf_urls(SONG_PAGE_RAW_TEXT_SIBLING_HTML, BASE)
        assert "Sheet Music" in result

    def test_anchor_text_used_as_fallback_label(self):
        # When there are no preceding text siblings the anchor's own text is used
        result = extract_pdf_urls(SONG_PAGE_ANCHOR_LABEL_HTML, BASE)
        assert "Download Lyrics PDF" in result
