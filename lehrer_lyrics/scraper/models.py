"""Pydantic models for the Tom Lehrer scraper data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, RootModel


class SongEntry(BaseModel):
    """A single song's scraped URLs.

    ``site`` is the canonical song page URL. All additional fields are PDF
    labels (e.g. ``"Lyrics"``, ``"Sheet music"``) mapped to their download URLs.
    """

    model_config = ConfigDict(extra="allow")

    site: str

    @property
    def pdf_urls(self) -> dict[str, str]:
        """Return the PDF label → URL mapping (all extra fields)."""
        return self.model_extra or {}


class SongCatalog(RootModel[dict[str, SongEntry]]):
    """The full catalog: song title → SongEntry."""
