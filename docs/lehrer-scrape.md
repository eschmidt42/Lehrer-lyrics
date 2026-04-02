# HTML Collector — `lehrer-scrape`

Dev-only CLI that scrapes [tomlehrersongs.com/songs](https://tomlehrersongs.com/songs/), caches HTML locally, and writes a JSON file mapping each song to its PDF URL(s).

Source: `src/lehrer_lyrics/scraper/`

---

## Setup

```bash
uv sync --group dev
```

---

## CLI usage

```bash
uv run lehrer-scrape [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--cache-dir PATH` | `.cache/html` | Directory for cached HTML files |
| `--output PATH` | `song-urls.json` | Output JSON file |
| `--delay FLOAT` | `2.0` | Seconds between live HTTP requests |
| `--force` | off | Re-fetch even if already cached |

**First run** — fetches all ~90 song pages live (~3 min at the default 2 s delay):

```bash
uv run lehrer-scrape
```

**Subsequent runs** — skips network requests for cached pages:

```bash
uv run lehrer-scrape --output song-urls-fresh.json
```

**Force re-fetch** all pages:

```bash
uv run lehrer-scrape --force
```

Progress is shown as a rolling window of the last 10 songs (spinner for the current page, ✓ for completed) with an overall progress bar showing N/total, elapsed time, and ETA.

---

## Output format

```json
{
  "All is Well": {
    "site": "https://tomlehrersongs.com/all-is-well/",
    "Lyrics": "https://tomlehrersongs.com/wp-content/uploads/2019/03/all-is-well.pdf"
  },
  "The Elements": {
    "site": "https://tomlehrersongs.com/the-elements/",
    "Lyrics": "https://tomlehrersongs.com/wp-content/uploads/…/the-elements.pdf",
    "Aristotle version": "https://tomlehrersongs.com/wp-content/uploads/…/the-elements-aristotle.pdf"
  }
}
```

- **Outer key** — song title extracted from the page's `<h1 class="entry-title">` (falls back to the link text on the listing page).
- **`"site"`** — URL of the song's page on tomlehrersongs.com.
- **Additional keys** — one per PDF link found on the song page. The key is the text immediately before the link (e.g. `"Lyrics"`, `"Revised version"`), with trailing colons and extra whitespace stripped.

---

## Module reference

### `fetcher.py` — `fetch_page`

```python
fetch_page(url, cache_dir, delay, force, *, _last_request_time=None) -> str
```

Fetches a URL and returns the raw HTML, reading from disk cache when available.

- Identifies itself as `lehrer-lyrics-scraper/0.1 (scraper bot; be nice)` in the `User-Agent` header.
- Enforces `delay` seconds between live requests using the shared `_last_request_time` list (pass the same list on every call within a session).
- Caches each page as `<cache_dir>/<slug>.html` where the slug is derived from the URL path.
- When `force=True` the cache is bypassed and the file is overwritten after fetching.

### `parser.py`

#### `extract_song_links(html, base_url) -> list[tuple[str, str]]`

Finds all relative `<a>` tags inside `<main id="main"> → <section id="content">` on the listing page. Returns `(title, absolute_url)` pairs. External (`http…`) and anchor (`#…`) links are skipped.

#### `extract_pdf_urls(html, base_url) -> dict[str, str]`

Finds all `<a href="….pdf">` tags inside the content section of a song page. For each, collects the text nodes preceding the link in the same parent element as the label, then cleans it (strips trailing `:`, collapses whitespace). Falls back to the anchor's own text when no preceding text is found.

#### `extract_song_title(html) -> str | None`

Returns the text of `<h1 class="entry-title">`, falling back to `<span class="entry-title">`, or `None` if neither is present.
