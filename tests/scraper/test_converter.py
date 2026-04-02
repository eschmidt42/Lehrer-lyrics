"""Unit tests for the converter module (retry / recovery logic)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import ollama
import pytest

from lehrer_lyrics.scraper.converter import (
    LLM_MAX_RETRIES,
    polish_lyrics_with_llm,
    wait_for_ollama_ready,
)

# ---------------------------------------------------------------------------
# wait_for_ollama_ready
# ---------------------------------------------------------------------------


def test_wait_for_ollama_ready_returns_immediately_when_server_up() -> None:
    with patch("lehrer_lyrics.scraper.converter.ollama.list") as mock_list:
        wait_for_ollama_ready(poll_interval=0.0, ready_timeout=5.0)
    mock_list.assert_called_once()


def test_wait_for_ollama_ready_retries_until_server_recovers() -> None:
    responses = [
        ollama.RequestError("down"),
        ollama.RequestError("down"),
        MagicMock(),  # success on third attempt
    ]
    with (
        patch(
            "lehrer_lyrics.scraper.converter.ollama.list",
            side_effect=responses,
        ),
        patch("lehrer_lyrics.scraper.converter.time.sleep") as mock_sleep,
    ):
        wait_for_ollama_ready(poll_interval=1.0, ready_timeout=60.0)

    assert mock_sleep.call_count == 2


def test_wait_for_ollama_ready_raises_after_timeout() -> None:
    with (
        patch(
            "lehrer_lyrics.scraper.converter.ollama.list",
            side_effect=ollama.RequestError("always down"),
        ),
        patch("lehrer_lyrics.scraper.converter.time.sleep"),
        patch(
            "lehrer_lyrics.scraper.converter.time.monotonic",
            side_effect=[0.0, 0.0, 200.0],  # deadline exceeded on third call
        ),
    ):
        with pytest.raises(ollama.RequestError):
            wait_for_ollama_ready(poll_interval=1.0, ready_timeout=5.0)


# ---------------------------------------------------------------------------
# polish_lyrics_with_llm — happy path
# ---------------------------------------------------------------------------


def test_polish_lyrics_returns_content_on_success() -> None:
    mock_response = MagicMock()
    mock_response.message.content = "# Song\n\nLyrics here.\n"

    with patch("lehrer_lyrics.scraper.converter.ollama.Client") as MockClient:
        MockClient.return_value.chat.return_value = mock_response
        result = polish_lyrics_with_llm("raw text", "model:7b")

    assert result == "# Song\n\nLyrics here.\n"


def test_polish_lyrics_returns_empty_string_when_content_is_none() -> None:
    mock_response = MagicMock()
    mock_response.message.content = None

    with patch("lehrer_lyrics.scraper.converter.ollama.Client") as MockClient:
        MockClient.return_value.chat.return_value = mock_response
        result = polish_lyrics_with_llm("raw text", "model:7b")

    assert result == ""


# ---------------------------------------------------------------------------
# polish_lyrics_with_llm — retry on RequestError
# ---------------------------------------------------------------------------


def test_polish_lyrics_retries_on_request_error_then_succeeds() -> None:
    mock_response = MagicMock()
    mock_response.message.content = "# Retry Success\n"

    chat_side_effects = [
        ollama.RequestError("timeout"),
        mock_response,
    ]

    with (
        patch("lehrer_lyrics.scraper.converter.ollama.Client") as MockClient,
        patch("lehrer_lyrics.scraper.converter.wait_for_ollama_ready") as mock_wait,
    ):
        MockClient.return_value.chat.side_effect = chat_side_effects
        result = polish_lyrics_with_llm("raw text", "model:7b", max_retries=3)

    assert result == "# Retry Success\n"
    mock_wait.assert_called_once()


def test_polish_lyrics_raises_after_all_retries_exhausted() -> None:
    with (
        patch("lehrer_lyrics.scraper.converter.ollama.Client") as MockClient,
        patch("lehrer_lyrics.scraper.converter.wait_for_ollama_ready"),
    ):
        MockClient.return_value.chat.side_effect = ollama.RequestError("stuck")
        with pytest.raises(ollama.RequestError):
            polish_lyrics_with_llm("raw text", "model:7b", max_retries=3)

    assert MockClient.return_value.chat.call_count == 3


def test_polish_lyrics_waits_between_retries_but_not_after_last() -> None:
    """wait_for_ollama_ready should be called max_retries-1 times (not after the final attempt)."""
    with (
        patch("lehrer_lyrics.scraper.converter.ollama.Client") as MockClient,
        patch("lehrer_lyrics.scraper.converter.wait_for_ollama_ready") as mock_wait,
    ):
        MockClient.return_value.chat.side_effect = ollama.RequestError("stuck")
        with pytest.raises(ollama.RequestError):
            polish_lyrics_with_llm("raw text", "model:7b", max_retries=3)

    assert mock_wait.call_count == LLM_MAX_RETRIES - 1


# ---------------------------------------------------------------------------
# polish_lyrics_with_llm — ResponseError is NOT retried
# ---------------------------------------------------------------------------


def test_polish_lyrics_does_not_retry_on_response_error() -> None:
    with (
        patch("lehrer_lyrics.scraper.converter.ollama.Client") as MockClient,
        patch("lehrer_lyrics.scraper.converter.wait_for_ollama_ready") as mock_wait,
    ):
        MockClient.return_value.chat.side_effect = ollama.ResponseError("bad model")
        with pytest.raises(ollama.ResponseError):
            polish_lyrics_with_llm("raw text", "model:7b", max_retries=3)

    MockClient.return_value.chat.assert_called_once()
    mock_wait.assert_not_called()
