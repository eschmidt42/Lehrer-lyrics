from fastapi.testclient import TestClient

from lehrer_lyrics.service.main import app

client = TestClient(app)


def test_root_returns_html_page():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "A CHRISTMAS CAROL" in response.text
    assert "Tom Lehrer" in response.text
