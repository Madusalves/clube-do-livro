"""Busca de livros na Open Library (API pública, sem chave). Só metadados e capas; nenhum livro é baixado."""
import httpx

SEARCH_URL = "https://openlibrary.org/search.json"
COVER_URL = "https://covers.openlibrary.org/b/id/{}-M.jpg"
COVER_PREFIX = "https://covers.openlibrary.org/"


def search(query: str, limit: int = 12) -> tuple[list[dict], bool]:
    """Devolve (resultados, ok). ok=False quando a Open Library não respondeu."""
    params = {
        "q": query,
        "limit": limit,
        "fields": "title,author_name,first_publish_year,cover_i,language",
    }
    try:
        r = httpx.get(SEARCH_URL, params=params, timeout=6, headers={"User-Agent": "clube-do-livro/1.0"})
        r.raise_for_status()
        docs = r.json().get("docs", [])
    except (httpx.HTTPError, ValueError):
        return [], False
    results = []
    for d in docs:
        if not d.get("title"):
            continue
        authors = d.get("author_name") or []
        results.append(
            {
                "title": d["title"],
                "author": ", ".join(authors[:2]) or "Autor desconhecido",
                "year": d.get("first_publish_year"),
                "cover_url": COVER_URL.format(d["cover_i"]) if d.get("cover_i") else "",
                "languages": ", ".join((d.get("language") or [])[:3]),
            }
        )
    return results, True
