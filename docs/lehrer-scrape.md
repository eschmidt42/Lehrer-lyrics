# Scraper CLI — `lehrer-scrape`

Dev-only CLI with three commands that form a pipeline:

- **`scrape`** — scrapes [tomlehrersongs.com/songs](https://tomlehrersongs.com/songs/), caches HTML locally, and writes a JSON file mapping each song to its PDF URL(s).
- **`download-pdfs`** — downloads all PDFs listed in that JSON to a local cache.
- **`pdf-to-markdown`** — reads cached lyrics PDFs, extracts text, and calls an Ollama LLM to produce clean Markdown files.

Source: `src/lehrer_lyrics/scraper/`

---

## Setup

```bash
uv sync --group dev
```

---

## Commands

### `scrape`

```bash
uv run lehrer-scrape scrape [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--cache-dir PATH` | `.cache/html` | Directory for cached HTML files |
| `--output PATH` | `song-urls.json` | Output JSON file |
| `--delay FLOAT` | `2.0` | Seconds between live HTTP requests |
| `--force` | off | Re-fetch even if already cached |

**First run** — fetches all ~90 song pages live (~3 min at the default 2 s delay):

```bash
uv run lehrer-scrape scrape
```

**Subsequent runs** — skips network requests for cached pages:

```bash
uv run lehrer-scrape scrape --output song-urls-fresh.json
```

**Force re-fetch** all pages:

```bash
uv run lehrer-scrape scrape --force
```

---

### `download-pdfs`

Reads the JSON produced by `scrape` and downloads every PDF to a local cache. Must be run after `scrape` (fails with a helpful message if the input file is missing).

```bash
uv run lehrer-scrape download-pdfs [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--input PATH` | `song-urls.json` | JSON file produced by `scrape` |
| `--cache-dir PATH` | `.cache/pdf` | Directory for cached PDF files |
| `--delay FLOAT` | `2.0` | Seconds between live HTTP requests |
| `--force` | off | Re-download even if already cached |

**Download all PDFs** (reads `song-urls.json`):

```bash
uv run lehrer-scrape download-pdfs
```

**Force re-download**:

```bash
uv run lehrer-scrape download-pdfs --force
```

Progress is shown as a rolling window of the last 10 songs (spinner for the current download, ✓ for completed) with an overall progress bar showing N/total, elapsed time, and ETA.

---

### `pdf-to-markdown`

Reads the JSON produced by `scrape`, finds every entry whose PDF label contains `"Lyrics"`, and converts each cached PDF to polished Markdown via an Ollama LLM. Skips sheet-music-only PDFs (filenames ending in `-music.pdf`, `-score.pdf`, `-final.pdf`, `-addenda.pdf`, `score-p.1.pdf`, `score-p.2.pdf`).

Requires [Ollama](https://ollama.com) to be running locally (default) or an Ollama cloud account (`--cloud`).

```bash
uv run lehrer-scrape pdf-to-markdown [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--input PATH` | `song-urls.json` | JSON file produced by `scrape` |
| `--pdf-cache-dir PATH` | `.cache/pdf` | Directory containing cached PDF files |
| `--output-dir PATH` | `.cache/markdown` | Directory for output Markdown files |
| `--model TEXT` | `ministral-3:14b` | Ollama model name |
| `--force` | off | Re-process PDFs even if Markdown already exists |
| `--llm-timeout FLOAT` | `60.0` | Per-request timeout (seconds) for the Ollama chat call |
| `--llm-max-retries INT` | `3` | Total attempts (first try + retries) on `RequestError` |
| `--poll-interval FLOAT` | `5.0` | Seconds between readiness polls while waiting for Ollama to recover |
| `--ready-timeout FLOAT` | `120.0` | Max seconds to wait for Ollama to become responsive after a failure |
| `--cloud` | off | Use Ollama cloud instead of a local server; prompts securely for API key |

**Local Ollama** — convert all lyrics PDFs (skips already-converted files):

```bash
uv run lehrer-scrape pdf-to-markdown
```

**Force re-process** all PDFs:

```bash
uv run lehrer-scrape pdf-to-markdown --force
```

**Ollama cloud**:

```bash
uv run lehrer-scrape pdf-to-markdown --cloud --model mistral-small:latest
# Enter Ollama API key: ****
```

**Pre-flight checks** (run before any conversion):

1. `song-urls.json` must exist and be readable.
2. For local Ollama: `ollama.list()` must succeed (server reachable).
3. For cloud: `ollama.Client(host="https://ollama.com", headers=...).list()` must succeed (API key valid).
4. The chosen `--model` must appear in the list of available models.

**Retry / recovery** — on `RequestError` or `ReadTimeout` the command:
1. Waits up to `--ready-timeout` seconds (polling every `--poll-interval` s) for Ollama to become responsive again.
2. Retries the LLM call up to `--llm-max-retries` times total.
3. If all retries fail, prints a warning and skips that song.

`ResponseError` (model / request error) is never retried — it warns and skips immediately.

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

This structure is modelled by `SongEntry` / `SongCatalog` in `models.py` (see below).

---

## Module reference

### `models.py`

#### `SongEntry`

Pydantic `BaseModel` representing one song's URLs. `site` is the declared field; all additional fields (PDF label → URL) are captured via `extra="allow"` and exposed through the `pdf_urls` property.

#### `SongCatalog`

Pydantic `RootModel[dict[str, SongEntry]]` representing the full catalog. Deserialise with `SongCatalog.model_validate_json(...)` and serialise with `.model_dump_json(indent=2)`.

---

### `fetcher.py`

#### `fetch_page`

```python
fetch_page(url, cache_dir, delay, force, *, _last_request_time=None) -> str
```

Fetches a URL and returns the raw HTML, reading from disk cache when available.

- Identifies itself as `lehrer-lyrics-scraper/0.1 (scraper bot; be nice)` in the `User-Agent` header.
- Enforces `delay` seconds between live requests using the shared `_last_request_time` list (pass the same list on every call within a session).
- Caches each page as `<cache_dir>/<slug>.html` where the slug is derived from the URL path.
- When `force=True` the cache is bypassed and the file is overwritten after fetching.

#### `fetch_binary`

```python
fetch_binary(url, cache_dir, delay, force, *, _last_request_time=None) -> bytes
```

Same rate-limiting and caching behaviour as `fetch_page`, but fetches binary content (e.g. PDFs). The cache filename is derived directly from the URL slug, which already carries the file extension (e.g. `alma.pdf`).

---

### `parser.py`

#### `extract_song_links(html, base_url) -> list[tuple[str, str]]`

Finds all relative `<a>` tags inside `<main id="main"> → <section id="content">` on the listing page. Returns `(title, absolute_url)` pairs. External (`http…`) and anchor (`#…`) links are skipped.

#### `extract_pdf_urls(html, base_url) -> dict[str, str]`

Finds all `<a href="….pdf">` tags inside the content section of a song page. For each, collects the text nodes preceding the link in the same parent element as the label, then cleans it (strips trailing `:`, collapses whitespace). Falls back to the anchor's own text when no preceding text is found.

#### `extract_song_title(html) -> str | None`

Returns the text of `<h1 class="entry-title">`, falling back to `<span class="entry-title">`, or `None` if neither is present.

---

### `converter.py`

#### `extract_text_from_pdf(pdf_path) -> str`

```python
extract_text_from_pdf(pdf_path: Path) -> str
```

Reads a PDF with `pypdf`, strips leading/trailing whitespace from each line on each page, and joins everything with newlines.

#### `build_messages(raw_text) -> list[dict]`

```python
build_messages(raw_text: str) -> list[dict[str, str]]
```

Returns a single-element list containing one `{"role": "user", "content": "…"}` message that embeds both the formatting instructions and the raw PDF text. Used as the `messages` argument for `ollama.Client.chat`.

#### `wait_for_ollama_ready`

```python
wait_for_ollama_ready(
    host: str | None = None,
    headers: dict | None = None,
    poll_interval: float = 5.0,
    ready_timeout: float = 120.0,
) -> None
```

Polls `ollama.Client(...).list()` until the server responds or `ready_timeout` seconds elapse. Raises `RuntimeError` on timeout. Passes `host`/`headers` through so cloud auth is preserved during retries.

#### `polish_lyrics_with_llm`

```python
polish_lyrics_with_llm(
    raw_text: str,
    model: str,
    host: str | None = None,
    headers: dict | None = None,
    timeout: float = 60.0,
    max_retries: int = 3,
    poll_interval: float = 5.0,
    ready_timeout: float = 120.0,
) -> str
```

Sends `build_messages(raw_text)` to `ollama.Client.chat` and returns the model's reply. On `RequestError` waits for Ollama to recover (via `wait_for_ollama_ready`) then retries up to `max_retries` times total. `ResponseError` propagates immediately without retrying.

#### `pdf_to_markdown`

```python
pdf_to_markdown(
    pdf_path: Path,
    output_path: Path,
    model: str,
    host: str | None = None,
    headers: dict | None = None,
    **kwargs,
) -> None
```

Extracts text from `pdf_path`, calls `polish_lyrics_with_llm`, and writes the result to `output_path`. All `**kwargs` are forwarded to `polish_lyrics_with_llm` (`timeout`, `max_retries`, `poll_interval`, `ready_timeout`).
