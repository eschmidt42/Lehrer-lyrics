"""Tests for the pdf-to-markdown CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from lehrer_lyrics.scraper.cli import app

runner = CliRunner()

SONG_DATA = {
    "Alma": {
        "site": "https://tomlehrersongs.com/alma/",
        "Lyrics": "https://tomlehrersongs.com/wp-content/uploads/2018/11/alma.pdf",
        "Sheet music": "https://tomlehrersongs.com/wp-content/uploads/2019/03/alma-music.pdf",
    },
    "Poisoning Pigeons": {
        "site": "https://tomlehrersongs.com/poisoning-pigeons-in-the-park/",
        "Lyrics": "https://tomlehrersongs.com/wp-content/uploads/2018/11/pigeons.pdf",
    },
}

_DEFAULT_MODEL = "qwen3.5:27b"


def _make_ollama_list(models: list[str]):
    """Build a fake ollama.list() return value with the given model names."""
    mock_list = MagicMock()
    mock_list.models = [MagicMock(model=m) for m in models]
    return mock_list


# ---------------------------------------------------------------------------
# Pre-flight: missing input file
# ---------------------------------------------------------------------------


def test_missing_input_exits_with_error(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "pdf-to-markdown",
            "--input",
            str(tmp_path / "nonexistent.json"),
        ],
    )

    assert result.exit_code == 1
    assert "not found" in result.output
    assert "scrape" in result.output


# ---------------------------------------------------------------------------
# Pre-flight: Ollama not reachable
# ---------------------------------------------------------------------------


def test_ollama_not_running_exits_with_error(tmp_path: Path) -> None:
    import ollama

    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps(SONG_DATA), encoding="utf-8")

    with patch(
        "lehrer_lyrics.scraper.cli.ollama.list",
        side_effect=ollama.RequestError("connection refused"),
    ):
        result = runner.invoke(
            app,
            ["pdf-to-markdown", "--input", str(input_file)],
        )

    assert result.exit_code == 1
    assert "not reachable" in result.output


# ---------------------------------------------------------------------------
# Pre-flight: model not available
# ---------------------------------------------------------------------------


def test_model_not_available_exits_with_error(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps(SONG_DATA), encoding="utf-8")

    with patch(
        "lehrer_lyrics.scraper.cli.ollama.list",
        return_value=_make_ollama_list(["other-model:7b"]),
    ):
        result = runner.invoke(
            app,
            ["pdf-to-markdown", "--input", str(input_file), "--model", _DEFAULT_MODEL],
        )

    assert result.exit_code == 1
    assert _DEFAULT_MODEL in result.output
    assert "not available" in result.output


# ---------------------------------------------------------------------------
# Successful conversion
# ---------------------------------------------------------------------------


def test_successful_conversion(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps(SONG_DATA), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    output_dir = tmp_path / "markdown"

    # Create fake cached PDFs for the two lyrics entries
    (pdf_cache / "wp-content_uploads_2018_11_alma.pdf").write_bytes(b"%PDF-1.4 fake")
    (pdf_cache / "wp-content_uploads_2018_11_pigeons.pdf").write_bytes(b"%PDF-1.4 fake")

    converted_titles: list[str] = []

    def fake_convert(pdf_path: Path, model: str, **kwargs: object) -> str:
        converted_titles.append(pdf_path.name)
        return f"# {pdf_path.stem}\n\nSome lyrics here.\n"

    with (
        patch(
            "lehrer_lyrics.scraper.cli.ollama.list",
            return_value=_make_ollama_list([_DEFAULT_MODEL]),
        ),
        patch("lehrer_lyrics.scraper.cli._convert_pdf", side_effect=fake_convert),
    ):
        result = runner.invoke(
            app,
            [
                "pdf-to-markdown",
                "--input",
                str(input_file),
                "--pdf-cache-dir",
                str(pdf_cache),
                "--output-dir",
                str(output_dir),
                "--model",
                _DEFAULT_MODEL,
            ],
        )

    assert result.exit_code == 0, result.output
    assert len(converted_titles) == 2
    # Sheet music PDF should NOT have been processed
    assert all("music" not in name for name in converted_titles)
    # Markdown files should exist
    assert (output_dir / "alma.md").exists()
    assert (output_dir / "pigeons.md").exists()
    assert "2 PDF(s)" in result.output


# ---------------------------------------------------------------------------
# Skip already-converted files
# ---------------------------------------------------------------------------


def test_skips_existing_markdown(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps({"Alma": SONG_DATA["Alma"]}), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    output_dir = tmp_path / "markdown"
    output_dir.mkdir()

    (pdf_cache / "wp-content_uploads_2018_11_alma.pdf").write_bytes(b"%PDF-1.4 fake")
    (output_dir / "alma.md").write_text(
        "# Alma\n\nExisting lyrics.\n", encoding="utf-8"
    )

    convert_calls: list[str] = []

    def fake_convert(pdf_path: Path, model: str) -> str:
        convert_calls.append(pdf_path.name)
        return "# Alma\n\nNew lyrics.\n"

    with (
        patch(
            "lehrer_lyrics.scraper.cli.ollama.list",
            return_value=_make_ollama_list([_DEFAULT_MODEL]),
        ),
        patch("lehrer_lyrics.scraper.cli._convert_pdf", side_effect=fake_convert),
    ):
        result = runner.invoke(
            app,
            [
                "pdf-to-markdown",
                "--input",
                str(input_file),
                "--pdf-cache-dir",
                str(pdf_cache),
                "--output-dir",
                str(output_dir),
            ],
        )

    assert result.exit_code == 0, result.output
    assert convert_calls == []  # converter was never called
    assert "1 skipped" in result.output
    # Existing file should be untouched
    assert "Existing lyrics" in (output_dir / "alma.md").read_text()


# ---------------------------------------------------------------------------
# --force flag re-processes existing files
# ---------------------------------------------------------------------------


def test_force_reprocesses_existing_markdown(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps({"Alma": SONG_DATA["Alma"]}), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    output_dir = tmp_path / "markdown"
    output_dir.mkdir()

    (pdf_cache / "wp-content_uploads_2018_11_alma.pdf").write_bytes(b"%PDF-1.4 fake")
    (output_dir / "alma.md").write_text("# Alma\n\nOld lyrics.\n", encoding="utf-8")

    def fake_convert(pdf_path: Path, model: str, **kwargs: object) -> str:
        return "# Alma\n\nNew lyrics.\n"

    with (
        patch(
            "lehrer_lyrics.scraper.cli.ollama.list",
            return_value=_make_ollama_list([_DEFAULT_MODEL]),
        ),
        patch("lehrer_lyrics.scraper.cli._convert_pdf", side_effect=fake_convert),
    ):
        result = runner.invoke(
            app,
            [
                "pdf-to-markdown",
                "--input",
                str(input_file),
                "--pdf-cache-dir",
                str(pdf_cache),
                "--output-dir",
                str(output_dir),
                "--force",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "New lyrics" in (output_dir / "alma.md").read_text()
    assert "1 PDF(s)" in result.output


# ---------------------------------------------------------------------------
# Missing PDF in cache
# ---------------------------------------------------------------------------


def test_warns_when_pdf_not_in_cache(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps({"Alma": SONG_DATA["Alma"]}), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    # No PDF files in cache

    with (
        patch(
            "lehrer_lyrics.scraper.cli.ollama.list",
            return_value=_make_ollama_list([_DEFAULT_MODEL]),
        ),
        patch("lehrer_lyrics.scraper.cli._convert_pdf") as mock_convert,
    ):
        result = runner.invoke(
            app,
            [
                "pdf-to-markdown",
                "--input",
                str(input_file),
                "--pdf-cache-dir",
                str(pdf_cache),
            ],
        )

    mock_convert.assert_not_called()
    assert result.exit_code == 0
    assert "0 PDF(s)" in result.output
    assert "1 skipped" in result.output


# ---------------------------------------------------------------------------
# Converter raises at runtime (RequestError / ResponseError)
# ---------------------------------------------------------------------------


def test_converter_request_error_warns_and_skips(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps({"Alma": SONG_DATA["Alma"]}), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    (pdf_cache / "wp-content_uploads_2018_11_alma.pdf").write_bytes(b"%PDF-1.4 fake")

    import ollama

    with (
        patch(
            "lehrer_lyrics.scraper.cli.ollama.list",
            return_value=_make_ollama_list([_DEFAULT_MODEL]),
        ),
        patch(
            "lehrer_lyrics.scraper.cli._convert_pdf",
            side_effect=ollama.RequestError("stuck after retries"),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "pdf-to-markdown",
                "--input",
                str(input_file),
                "--pdf-cache-dir",
                str(pdf_cache),
            ],
        )

    assert result.exit_code == 0
    assert "failed to convert" in result.output
    assert "0 PDF(s)" in result.output
    assert "1 skipped" in result.output


def test_converter_response_error_warns_and_skips(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps({"Alma": SONG_DATA["Alma"]}), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    (pdf_cache / "wp-content_uploads_2018_11_alma.pdf").write_bytes(b"%PDF-1.4 fake")

    import ollama

    with (
        patch(
            "lehrer_lyrics.scraper.cli.ollama.list",
            return_value=_make_ollama_list([_DEFAULT_MODEL]),
        ),
        patch(
            "lehrer_lyrics.scraper.cli._convert_pdf",
            side_effect=ollama.ResponseError("model error"),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "pdf-to-markdown",
                "--input",
                str(input_file),
                "--pdf-cache-dir",
                str(pdf_cache),
            ],
        )

    assert result.exit_code == 0
    assert "failed to convert" in result.output
    assert "1 skipped" in result.output
