from pathlib import Path

import markdown
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fasthtml.common import (
    Body,
    Footer,
    Head,
    Html,
    Link,
    Main,
    Meta,
    NotStr,
    Title,
    to_xml,
)

_SONGS_DIR = Path(__file__).parent / "songs"
_PICO_CSS = Link(
    rel="stylesheet",
    href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css",
)


def _render_song(path: Path) -> str:
    """Read a markdown song file and return rendered HTML string."""
    return markdown.markdown(path.read_text(encoding="utf-8"), extensions=["nl2br"])


# Rendered once at startup — no per-request overhead
_CHRISTMAS_CAROL_HTML = _render_song(_SONGS_DIR / "a-christmas-carol.md")

_PAGE = to_xml(
    Html(
        Head(
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            _PICO_CSS,
            Title("A Christmas Carol — Tom Lehrer"),
        ),
        Body(
            Main(
                NotStr(_CHRISTMAS_CAROL_HTML),
                cls="container",
                style="max-width:48rem;margin:4rem auto;text-align:center;",
            ),
            Footer(
                NotStr(
                    "By Tom Lehrer &mdash; <em>Going from adolescence to senility, trying to bypass maturity</em>"
                ),
                cls="container",
                style="max-width:48rem;margin:2rem auto;text-align:center;font-size:.85rem;color:var(--pico-muted-color);",
            ),
        ),
        lang="en",
    )
)

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(content=_PAGE)
