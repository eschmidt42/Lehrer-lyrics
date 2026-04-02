## General

- When answering questions about frameworks, libraries, or APIs, use Context7 to retrieve current documentation rather than relying on training data.

## Build Commands

- `uv run pytest tests --cov --cov-branch --cov-report=xml` - Compute test coverage.
- `uv run pytest -n auto tests` - Run all tests
- `uv sync` - Update / align dependencies in `.venv` / `uv.lock` with `pyproject.toml`
- `uv run ty check YOURPATH` - Run type check on YOURPATH (variable to be replaced)

## Workflow

- Run `prek run --all-files` after making changes.
