"""Tests for the pdf-to-markdown CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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

_DEFAULT_MODEL = "ministral-3:14b"


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

    def fake_convert(pdf_path: Path, model: str, **kwargs: object) -> str:
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
                "--output-dir",
                str(tmp_path / "markdown"),
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
                "--output-dir",
                str(tmp_path / "markdown"),
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
                "--output-dir",
                str(tmp_path / "markdown"),
            ],
        )

    assert result.exit_code == 0
    assert "failed to convert" in result.output
    assert "1 skipped" in result.output


# ---------------------------------------------------------------------------
# Music / score / addenda filename filtering
# ---------------------------------------------------------------------------

_FILTERED_SUFFIXES = [
    "-music.pdf",
    "-score.pdf",
    "-final.pdf",
    "score-p.1.pdf",
    "score-p.2.pdf",
    "-addenda.pdf",
]


def test_music_and_score_files_are_skipped(tmp_path: Path) -> None:
    """PDFs whose names end with known non-lyrics suffixes must be silently skipped."""
    # Build a catalog with one song that has both a lyrics and several filtered PDFs
    song_data = {
        "Alma": {
            "site": "https://tomlehrersongs.com/alma/",
            "Lyrics": "https://tomlehrersongs.com/wp-content/uploads/2018/11/alma.pdf",
            "Sheet music": "https://tomlehrersongs.com/wp-content/uploads/2019/03/alma-music.pdf",
        }
    }
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps(song_data), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    output_dir = tmp_path / "markdown"
    (pdf_cache / "wp-content_uploads_2018_11_alma.pdf").write_bytes(b"%PDF-1.4 fake")

    convert_calls: list[str] = []

    def recording_convert(pdf_path: Path, model: str, **kwargs: object) -> str:
        convert_calls.append(pdf_path.name)
        return "# Alma\n\nLyrics.\n"

    with (
        patch(
            "lehrer_lyrics.scraper.cli.ollama.list",
            return_value=_make_ollama_list([_DEFAULT_MODEL]),
        ),
        patch("lehrer_lyrics.scraper.cli._convert_pdf", side_effect=recording_convert),
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
    # Sheet music URL ends in -music.pdf but it is also NOT a "Lyrics" label,
    # so it wouldn't be in the task list at all — the test verifies the lyrics PDF
    # is processed and the music PDF is simply absent from convert_calls.
    assert len(convert_calls) == 1
    assert convert_calls[0] == "wp-content_uploads_2018_11_alma.pdf"


@pytest.mark.parametrize("suffix", _FILTERED_SUFFIXES)
def test_filtered_suffix_is_not_converted(suffix: str, tmp_path: Path) -> None:
    """A lyrics-labelled PDF whose name ends with a filtered suffix is skipped."""
    filename = f"wp-content_uploads_2018_11_alma{suffix}"
    url = f"https://tomlehrersongs.com/wp-content/uploads/2018/11/alma{suffix}"
    song_data = {
        "Alma": {
            "site": "https://tomlehrersongs.com/alma/",
            "Lyrics": url,
        }
    }
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps(song_data), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    (pdf_cache / filename).write_bytes(b"%PDF-1.4 fake")

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
                "--output-dir",
                str(tmp_path / "markdown"),
            ],
        )

    mock_convert.assert_not_called()
    assert result.exit_code == 0, result.output
    assert "1 skipped" in result.output


# ---------------------------------------------------------------------------
# ReadTimeout is handled like RequestError
# ---------------------------------------------------------------------------


def test_read_timeout_warns_and_skips(tmp_path: Path) -> None:
    from httpx import ReadTimeout

    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps({"Alma": SONG_DATA["Alma"]}), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    (pdf_cache / "wp-content_uploads_2018_11_alma.pdf").write_bytes(b"%PDF-1.4 fake")

    with (
        patch(
            "lehrer_lyrics.scraper.cli.ollama.list",
            return_value=_make_ollama_list([_DEFAULT_MODEL]),
        ),
        patch(
            "lehrer_lyrics.scraper.cli._convert_pdf",
            side_effect=ReadTimeout("timed out"),
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
                "--output-dir",
                str(tmp_path / "markdown"),
            ],
        )

    assert result.exit_code == 0
    assert "failed to convert" in result.output
    assert "1 skipped" in result.output


def _make_cloud_client_mock(models: list[str]) -> MagicMock:
    """Return a mock that behaves like an ollama.Client for cloud pre-flight."""
    mock_client = MagicMock()
    mock_client.list.return_value = _make_ollama_list(models)
    return mock_client


def test_cloud_prompts_for_api_key_and_succeeds(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps({"Alma": SONG_DATA["Alma"]}), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    (pdf_cache / "wp-content_uploads_2018_11_alma.pdf").write_bytes(b"%PDF-1.4 fake")

    mock_cloud_client = _make_cloud_client_mock([_DEFAULT_MODEL])

    with (
        patch(
            "lehrer_lyrics.scraper.cli.ollama.Client",
            return_value=mock_cloud_client,
        ),
        patch(
            "lehrer_lyrics.scraper.cli._convert_pdf",
            return_value="# Alma\n\nCloud lyrics.\n",
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
                "--output-dir",
                str(tmp_path / "markdown"),
                "--model",
                _DEFAULT_MODEL,
                "--cloud",
            ],
            input="my-secret-api-key\n",
        )

    assert result.exit_code == 0, result.output
    assert "1 PDF(s)" in result.output


def test_cloud_request_error_exits_with_error(tmp_path: Path) -> None:
    import ollama

    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps(SONG_DATA), encoding="utf-8")

    mock_cloud_client = MagicMock()
    mock_cloud_client.list.side_effect = ollama.RequestError("network failure")

    with patch(
        "lehrer_lyrics.scraper.cli.ollama.Client", return_value=mock_cloud_client
    ):
        result = runner.invoke(
            app,
            ["pdf-to-markdown", "--input", str(input_file), "--cloud"],
            input="bad-key\n",
        )

    assert result.exit_code == 1
    assert "cloud API" in result.output
    assert "not reachable" in result.output


def test_cloud_response_error_exits_with_api_key_hint(tmp_path: Path) -> None:
    import ollama

    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps(SONG_DATA), encoding="utf-8")

    mock_cloud_client = MagicMock()
    mock_cloud_client.list.side_effect = ollama.ResponseError("401 Unauthorized")

    with patch(
        "lehrer_lyrics.scraper.cli.ollama.Client", return_value=mock_cloud_client
    ):
        result = runner.invoke(
            app,
            ["pdf-to-markdown", "--input", str(input_file), "--cloud"],
            input="wrong-key\n",
        )

    assert result.exit_code == 1
    assert "API key" in result.output


def test_cloud_model_not_available_exits_with_error(tmp_path: Path) -> None:
    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps(SONG_DATA), encoding="utf-8")

    mock_cloud_client = _make_cloud_client_mock(["other-model:7b"])

    with patch(
        "lehrer_lyrics.scraper.cli.ollama.Client", return_value=mock_cloud_client
    ):
        result = runner.invoke(
            app,
            [
                "pdf-to-markdown",
                "--input",
                str(input_file),
                "--model",
                _DEFAULT_MODEL,
                "--cloud",
            ],
            input="my-key\n",
        )

    assert result.exit_code == 1
    assert _DEFAULT_MODEL in result.output
    assert "not available" in result.output


def test_cloud_host_and_headers_forwarded_to_converter(tmp_path: Path) -> None:
    """_convert_pdf must receive host=_CLOUD_HOST and the Bearer headers."""
    from lehrer_lyrics.scraper.cli import _CLOUD_HOST

    input_file = tmp_path / "song-urls.json"
    input_file.write_text(json.dumps({"Alma": SONG_DATA["Alma"]}), encoding="utf-8")

    pdf_cache = tmp_path / "pdf"
    pdf_cache.mkdir()
    (pdf_cache / "wp-content_uploads_2018_11_alma.pdf").write_bytes(b"%PDF-1.4 fake")

    mock_cloud_client = _make_cloud_client_mock([_DEFAULT_MODEL])
    convert_calls: list[dict] = []

    def recording_convert(pdf_path, model, **kwargs):  # type: ignore[no-untyped-def]
        convert_calls.append(kwargs)
        return "# Alma\n\nLyrics.\n"

    with (
        patch(
            "lehrer_lyrics.scraper.cli.ollama.Client", return_value=mock_cloud_client
        ),
        patch("lehrer_lyrics.scraper.cli._convert_pdf", side_effect=recording_convert),
    ):
        runner.invoke(
            app,
            [
                "pdf-to-markdown",
                "--input",
                str(input_file),
                "--pdf-cache-dir",
                str(pdf_cache),
                "--output-dir",
                str(tmp_path / "markdown"),
                "--cloud",
            ],
            input="secret\n",
        )

    assert len(convert_calls) == 1
    assert convert_calls[0]["host"] == _CLOUD_HOST
    assert convert_calls[0]["headers"] == {"Authorization": "Bearer secret"}
