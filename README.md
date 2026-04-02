# lehrer-lyrics

> Lehrer lyrics in all their glory, [one song to brighten your day](https://lehrer-lyrics.fastapicloud.dev).

[![CI](https://github.com/eschmidt42/Lehrer-lyrics/actions/workflows/ci.yml/badge.svg)](https://github.com/eschmidt42/Lehrer-lyrics/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/eschmidt42/Lehrer-lyrics/branch/main/graph/badge.svg?token=FM1L1A7BQ8)](https://codecov.io/gh/eschmidt42/Lehrer-lyrics)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)
[![prek](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/j178/prek/master/docs/assets/badge-v0.json)](https://github.com/j178/prek)

A project created with [FastAPI cloud](https://fastapicloud.com) CLI -> [docs](./docs/fastapi-cloud.md).

## Scraper CLI

A dev-only CLI (`lehrer-scrape`) with four commands that form a pipeline:

```bash
uv sync --group dev

# 1. Scrape song pages → song-urls.json
uv run lehrer-scrape scrape

# 2. Download PDFs → .cache/pdf/
uv run lehrer-scrape download-pdfs

# 3. Convert lyrics PDFs to Markdown → .cache/markdown/  (requires Ollama)
uv run lehrer-scrape pdf-to-markdown                     # local Ollama
uv run lehrer-scrape pdf-to-markdown --cloud             # Ollama cloud (prompts for API key)

# 4. Build SQLite database → lehrer_lyrics/service/songs.db  (commit to repo)
uv run lehrer-scrape build-db
```

See [docs/lehrer-scrape.md](./docs/lehrer-scrape.md) for full CLI and module documentation.

## Service

A FastAPI app (`lehrer_lyrics/service/main.py`) that serves one Tom Lehrer song per day.

**How it works:**

- On startup, all songs are loaded once from `lehrer_lyrics/service/songs.db` (a SQLite database built by `lehrer-scrape build-db`) and cached in memory.
- Each request to `GET /` picks today's song by seeding Python's `random.Random` with the current date in the Europe/Berlin timezone — everyone sees the same song all day, and it changes deterministically at midnight Berlin time.
- Lyrics are stored as zlib-compressed Markdown blobs in the database. They are decompressed and rendered to HTML (with `nl2br` for line-break preservation) on the first request of each day, then cached.
- If the database is empty the service falls back to a bundled "A Christmas Carol" file.
- Static assets (CSS) are served from `/static`.
