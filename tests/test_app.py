import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLUBE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("CLUBE_UPLOADS", str(tmp_path / "uploads"))
    from app import db, main

    importlib.reload(db)
    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def add_book(client, title="Dom Casmurro", author="Machado de Assis", **extra):
    r = client.post("/livros", data={"title": title, "author": author, **extra}, follow_redirects=False)
    assert r.status_code == 303
    return int(r.headers["location"].rsplit("/", 1)[1])


def test_home_empty(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "ainda não escolheu" in r.text


def test_add_book_is_idempotent(client):
    a = add_book(client)
    b = add_book(client, title="dom casmurro", author="machado de assis")
    assert a == b


def test_review_upsert_and_average(client):
    book = add_book(client)
    for name, rating in [("Ana", 5), ("Bruno", 3)]:
        r = client.post(f"/livros/{book}/resenha", data={"member_name": name, "rating": rating, "text": "ok"},
                        follow_redirects=False)
        assert r.status_code == 303
    # Ana muda de ideia: atualiza em vez de duplicar
    client.post(f"/livros/{book}/resenha", data={"member_name": "ana", "rating": 1, "text": "mudei"})
    page = client.get(f"/livros/{book}").text
    assert page.count("<article") == 2
    assert "mudei" in page
    assert "2.0" in page  # (1 + 3) / 2


def test_invalid_rating_rejected(client):
    book = add_book(client)
    r = client.post(f"/livros/{book}/resenha", data={"member_name": "Ana", "rating": 9, "text": ""})
    assert r.status_code == 400


def test_current_book_cycles(client):
    a, b = add_book(client), add_book(client, title="Capitães da Areia", author="Jorge Amado")
    client.post(f"/livros/{a}/atual")
    assert "Dom Casmurro" in client.get("/").text
    client.post(f"/livros/{b}/atual")  # troca encerra o ciclo anterior
    home = client.get("/").text
    assert "Capitães da Areia" in home
    hist = client.get("/historico").text
    assert "Dom Casmurro" in hist and "em andamento" in hist
    client.post("/ciclo/encerrar")
    assert "ainda não escolheu" in client.get("/").text


def test_404s(client):
    assert client.get("/livros/999").status_code == 404
    assert client.get("/membros/999").status_code == 404


def test_cover_upload(client):
    r = client.post("/livros", data={"title": "A", "author": "B"},
                    files={"cover": ("c.png", b"PNG fake", "image/png")}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"]).text
    url = page.split('src="')[1].split('"')[0]
    assert url.startswith("/uploads/")
    assert client.get(url).status_code == 200


def test_cover_rejects_non_image(client):
    r = client.post("/livros", data={"title": "A", "author": "B"},
                    files={"cover": ("x.txt", b"oi", "text/plain")})
    assert r.status_code == 400


def test_search_local_and_external(client, monkeypatch):
    from app import main

    add_book(client)
    fake = [{"title": "O Hobbit", "author": "Tolkien", "year": 1937,
             "cover_url": "https://covers.openlibrary.org/b/id/1-M.jpg", "languages": "por"}]
    monkeypatch.setattr(main.openlibrary, "search", lambda q: (fake, True))
    page = client.get("/buscar", params={"q": "casmurro"}).text
    assert "Dom Casmurro" in page and "O Hobbit" in page

    r = client.post("/livros/importar", data={"title": "O Hobbit", "author": "Tolkien", "year": "1937",
                    "cover_url": "https://covers.openlibrary.org/b/id/1-M.jpg"}, follow_redirects=False)
    assert r.status_code == 303
    assert "covers.openlibrary.org" in client.get(r.headers["location"]).text


def test_import_ignores_foreign_cover(client):
    r = client.post("/livros/importar", data={"title": "X", "author": "Y", "cover_url": "http://evil.example/a.jpg"},
                    follow_redirects=False)
    assert "evil.example" not in client.get(r.headers["location"]).text


def test_search_survives_openlibrary_down(client, monkeypatch):
    from app import main

    monkeypatch.setattr(main.openlibrary, "search", lambda q: ([], False))
    page = client.get("/buscar", params={"q": "x"})
    assert page.status_code == 200 and "Não foi possível consultar" in page.text
