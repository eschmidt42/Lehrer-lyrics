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

## HTML collector

A dev-only CLI that scrapes [tomlehrersongs.com/songs](https://tomlehrersongs.com/songs/), caches HTML locally, and writes a JSON file mapping each song to its PDF URL(s).

```bash
uv sync --group dev
uv run lehrer-scrape scrape           # fetch all ~90 song pages (2 s delay between requests)
uv run lehrer-scrape scrape --force   # re-fetch even if cached
```

## PDF downloader

Downloads all PDFs for every song listed in the JSON produced by the HTML collector.

```bash
uv run lehrer-scrape download-pdfs           # download all PDFs (reads song-urls.json)
uv run lehrer-scrape download-pdfs --force   # re-download even if already cached
```

See [docs/lehrer-scrape.md](./docs/lehrer-scrape.md) for full CLI and module documentation.
