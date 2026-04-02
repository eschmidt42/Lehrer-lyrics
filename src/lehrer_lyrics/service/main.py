from pathlib import Path

import markdown
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
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

_SERVICE_DIR = Path(__file__).parent
_SONGS_DIR = _SERVICE_DIR / "songs"
_PICO_CSS = Link(
    rel="stylesheet",
    href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css",
)
_LOCAL_CSS = Link(rel="stylesheet", href="/static/style.css")


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
            _LOCAL_CSS,
            Title("A Christmas Carol — Tom Lehrer"),
        ),
        Body(
            Main(
                NotStr(_CHRISTMAS_CAROL_HTML),
                cls="container",
            ),
            Footer(
                NotStr(
                    "By Tom Lehrer &mdash; <em>Going from adolescence to senility, trying to bypass maturity</em>"
                ),
                cls="container",
            ),
        ),
        lang="en",
    )
)

app = FastAPI()
app.mount("/static", StaticFiles(directory=_SERVICE_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(content=_PAGE)
