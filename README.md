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

A dev-only CLI (`lehrer-scrape`) with three commands that form a pipeline:

```bash
uv sync --group dev

# 1. Scrape song pages → song-urls.json
uv run lehrer-scrape scrape

# 2. Download PDFs → .cache/pdf/
uv run lehrer-scrape download-pdfs

# 3. Convert lyrics PDFs to Markdown → .cache/markdown/  (requires Ollama)
uv run lehrer-scrape pdf-to-markdown                     # local Ollama
uv run lehrer-scrape pdf-to-markdown --cloud             # Ollama cloud (prompts for API key)
```

See [docs/lehrer-scrape.md](./docs/lehrer-scrape.md) for full CLI and module documentation.
