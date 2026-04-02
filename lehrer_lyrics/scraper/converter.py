"""PDF-to-markdown conversion using pypdf and a local Ollama LLM."""

from __future__ import annotations

import time
from pathlib import Path

import ollama
import pypdf

# _SYSTEM_PROMPT = """You are a lyrics formatting assistant.

# Given raw text extracted from a PDF, return only the song lyrics in clean Markdown.

# Use a level-1 heading for the song title, separate stanzas with a blank line, and do not include any commentary, notes, or extra text.

# Use the following structure:
# """

_SYSTEM_PROMPT = """Convert the following lyrics extracted from a PDF into clean Markdown.

Please:
1. Identify and bold the title (remove the — or header noise).
2. Extract the credits and place them below the title in bold italics.
3. Group lines into logical stanzas using double line breaks (verse-chorus structure).
4. Handle footnotes by moving the text associated with, e.g. `(*)`, to a blockquote at the end.
5. Return the lyrics without adding comments from your side."""


# How long (seconds) to wait for a single chat response before giving up.
LLM_TIMEOUT: float = 60.0
# How many times to retry a failed chat call.
LLM_MAX_RETRIES: int = 3
# Seconds between readiness polls after a failure.
_POLL_INTERVAL: float = 5.0
# Maximum seconds to wait for Ollama to become responsive again.
_READY_TIMEOUT: float = 120.0


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract raw text from a PDF file using pypdf."""
    reader = pypdf.PdfReader(str(pdf_path))
    parts = [page.extract_text() or "" for page in reader.pages]
    parts = [page.split("\n") for page in parts]
    parts = [[line.strip() for line in page] for page in parts]
    parts = ["\n".join(page) for page in parts]
    return "\n".join(parts)


def wait_for_ollama_ready(
    *,
    poll_interval: float = _POLL_INTERVAL,
    ready_timeout: float = _READY_TIMEOUT,
    host: str | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """Block until the Ollama server responds to a list request or the timeout expires.

    This is called between retry attempts so that we don't immediately hammer a
    temporarily stuck server.

    Args:
        poll_interval: Seconds between successive readiness checks.
        ready_timeout: Maximum seconds to wait before giving up.
        host: Ollama host URL.  ``None`` uses the default (local) host.
        headers: Extra HTTP headers (e.g. ``{"Authorization": "Bearer …"}`` for cloud).

    Raises:
        ollama.RequestError: If the server is still unreachable after *ready_timeout* seconds.
    """
    client = ollama.Client(host=host, headers=headers)
    deadline = time.monotonic() + ready_timeout
    last_exc: ollama.RequestError | None = None
    while time.monotonic() < deadline:
        try:
            client.list()
            return
        except ollama.RequestError as exc:
            last_exc = exc
            time.sleep(poll_interval)
    raise last_exc or ollama.RequestError(
        "Ollama server did not recover within the timeout"
    )


def build_messages(raw_text: str) -> list[dict[str, str]]:
    return [
        # {"role": "system", "content": _SYSTEM_PROMPT},
        # {"role": "user", "content": f"Text: {raw_text}"},
        {
            "role": "user",
            "content": f"""Convert the following Tom Lehrer lyrics extracted from a PDF into clean Markdown.

Please:
1. Identify and bold the title (remove the — or header noise).
2. Extract the credits and place them below the title in bold italics.
3. Group lines into logical stanzas using double line breaks (verse-chorus structure).
4. Handle footnotes by moving the text associated with, e.g. `(*)`, to a blockquote at the end.

---

{raw_text}""",
        }
    ]


def polish_lyrics_with_llm(
    raw_text: str,
    model: str,
    *,
    timeout: float = LLM_TIMEOUT,
    max_retries: int = LLM_MAX_RETRIES,
    poll_interval: float = _POLL_INTERVAL,
    ready_timeout: float = _READY_TIMEOUT,
    host: str | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    """Send raw PDF text to a local Ollama model and return polished Markdown lyrics.

    On a ``RequestError`` (server unreachable or timed out) the function waits
    until Ollama is responsive again via :func:`wait_for_ollama_ready`, then
    retries up to *max_retries* times total.

    Args:
        raw_text: Raw text extracted from the lyrics PDF.
        model: Ollama model identifier (e.g. ``"qwen3.5:27b"``).
        timeout: Per-request timeout in seconds passed to the HTTP client.
        max_retries: Total number of attempts (first try + retries).
        poll_interval: Seconds between readiness polls after a failure.
        ready_timeout: Maximum seconds to wait for Ollama to recover before giving up.
        host: Ollama host URL.  ``None`` uses the default (local) host.
        headers: Extra HTTP headers (e.g. ``{"Authorization": "Bearer …"}`` for cloud).

    Raises:
        ollama.RequestError: If the server is unreachable after all retries.
        ollama.ResponseError: If the model returns an error response.
    """
    client = ollama.Client(host=host, headers=headers, timeout=timeout)
    last_exc: ollama.RequestError | ollama.ResponseError | None = None

    for attempt in range(max_retries):
        try:
            response = client.chat(
                model=model,
                messages=build_messages(raw_text),
            )
            return response.message.content or ""
        except ollama.RequestError as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                wait_for_ollama_ready(
                    poll_interval=poll_interval,
                    ready_timeout=ready_timeout,
                    host=host,
                    headers=headers,
                )
        except ollama.ResponseError as exc:
            # ResponseError is not a connectivity issue — don't retry.
            raise exc from None

    if last_exc is not None:
        raise last_exc
    raise ollama.RequestError(
        f"polish_lyrics_with_llm failed after {max_retries} attempts"
    )


def pdf_to_markdown(
    pdf_path: Path,
    model: str,
    *,
    timeout: float = LLM_TIMEOUT,
    max_retries: int = LLM_MAX_RETRIES,
    poll_interval: float = _POLL_INTERVAL,
    ready_timeout: float = _READY_TIMEOUT,
    host: str | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    """Extract text from a PDF and polish it into Markdown lyrics via an LLM."""
    raw_text = extract_text_from_pdf(pdf_path)
    return polish_lyrics_with_llm(
        raw_text,
        model,
        timeout=timeout,
        max_retries=max_retries,
        poll_interval=poll_interval,
        ready_timeout=ready_timeout,
        host=host,
        headers=headers,
    )
