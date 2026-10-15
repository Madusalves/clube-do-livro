import os
import uuid
from datetime import date
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from markupsafe import Markup
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, openlibrary

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

UPLOADS = Path(os.environ.get("CLUBE_UPLOADS", BASE.parent / "uploads"))
UPLOADS.mkdir(parents=True, exist_ok=True)
COVER_EXTS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
MAX_COVER_BYTES = 5 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Lê aí, Uai", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")


async def save_cover(file: UploadFile | None) -> str | None:
    if file is None or not file.filename:
        return None
    ext = COVER_EXTS.get(file.content_type)
    if not ext:
        raise HTTPException(400, "A capa deve ser uma imagem (JPG, PNG, WebP ou GIF).")
    data = await file.read(MAX_COVER_BYTES + 1)
    if len(data) > MAX_COVER_BYTES:
        raise HTTPException(400, "A capa deve ter no máximo 5 MB.")
    if not data:
        return None
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS / name).write_bytes(data)
    return f"/uploads/{name}"


def stars(n):
    n = int(round(n or 0))
    return "★" * n + "☆" * (5 - n)


templates.env.filters["stars"] = stars

# Ícones de traço (viewBox 24x24) herdam a cor do texto via currentColor.
ICONS = {
    "book": '<path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h10"/><path d="M9 8h5"/>',
    "open": '<path d="M12 6c-2-1.5-5-2-8-1.5v13c3-.5 6 0 8 1.5 2-1.5 5-2 8-1.5v-13c-3-.5-6 0-8 1.5z"/><path d="M12 6v13"/>',
    "bookmark": '<path d="M7 3h10v18l-5-4-5 4z"/>',
    "quill": '<path d="M20 4c-7 0-12 4-13 11l-3 5 5-3c7-1 11-6 11-13z"/><path d="M9 15l7-7"/>',
    "stack": '<rect x="4" y="15" width="16" height="4" rx="1"/><rect x="6" y="10" width="13" height="4" rx="1"/><rect x="5" y="5" width="14" height="4" rx="1"/>',
    "glasses": '<circle cx="7" cy="14" r="3.5"/><circle cx="17" cy="14" r="3.5"/><path d="M10.5 14h3M3.5 14L5 8M20.5 14L19 8"/>',
    "cup": '<path d="M5 9h12v5a5 5 0 0 1-5 5h-2a5 5 0 0 1-5-5z"/><path d="M17 10h1.5a2.5 2.5 0 0 1 0 5H17"/><path d="M9 3c-1 1 1 2 0 3M13 3c-1 1 1 2 0 3"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    "feather": '<path d="M4 20L16 8"/><path d="M16 8c1-3 3-4 5-4 0 2-1 4-4 5M12 12c1-2 2-3 4-4M8 16c1-2 2-3 4-4"/>',
}


def icon(name: str, size: int = 20) -> Markup:
    return Markup(
        f'<svg class="ico" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{ICONS[name]}</svg>'
    )


templates.env.globals["icon"] = icon


def go(path: str):
    return RedirectResponse(path, status_code=303)


# ---------- páginas ----------

@app.get("/")
def home(request: Request):
    with db.connect() as conn:
        ctx = {
            "current": db.current_cycle(conn),
            "recent": db.recent_reviews(conn),
            "cycles": db.list_cycles(conn)[:5],
        }
        cur = ctx["current"]
        ctx["current_book"] = db.get_book(conn, cur["book_id"]) if cur else None
    return templates.TemplateResponse(request, "home.html", ctx)


@app.get("/buscar")
def search(request: Request, q: str = ""):
    q = q.strip()
    local, external, external_ok = [], [], True
    if q:
        with db.connect() as conn:
            local = db.search_books(conn, q)
        known = {(b["title"].lower(), b["author"].lower()) for b in local}
        external, external_ok = openlibrary.search(q)
        external = [e for e in external if (e["title"].lower(), e["author"].lower()) not in known]
    return templates.TemplateResponse(
        request,
        "search.html",
        {"q": q, "local": local, "external": external, "external_ok": external_ok},
    )


@app.post("/livros/importar")
def import_book(
    title: str = Form(...),
    author: str = Form(...),
    year: str = Form(""),
    cover_url: str = Form(""),
):
    cover_url = cover_url.strip()
    if not cover_url.startswith(openlibrary.COVER_PREFIX):
        cover_url = ""
    year_val = int(year) if year.strip().isdigit() else None
    with db.connect() as conn:
        book_id = db.add_book(conn, title, author, year_val, cover_url)
    return go(f"/livros/{book_id}")


@app.get("/livros")
def books(request: Request):
    with db.connect() as conn:
        return templates.TemplateResponse(request, "books.html", {"books": db.list_books(conn)})


def parse_read_on(value: str) -> str:
    """Data da leitura passada: vazio vira hoje; aceita AAAA-MM-DD ou AAAA-MM."""
    value = value.strip()
    if not value:
        return date.today().isoformat()
    try:
        return date.fromisoformat(value if len(value) > 7 else value + "-01").isoformat()
    except ValueError:
        raise HTTPException(400, "Data inválida.")


@app.post("/livros")
async def create_book(
    title: str = Form(...),
    author: str = Form(...),
    year: str = Form(""),
    cover: UploadFile | None = File(None),
    suggested_by: str = Form(""),
    past: str = Form(""),
    read_on: str = Form(""),
):
    if not title.strip() or not author.strip():
        raise HTTPException(400, "Título e autor são obrigatórios.")
    year_val = int(year) if year.strip().isdigit() else None
    read_date = parse_read_on(read_on) if past else None
    cover_url = await save_cover(cover)
    with db.connect() as conn:
        member_id = db.get_or_create_member(conn, suggested_by) if suggested_by.strip() else None
        book_id = db.add_book(conn, title, author, year_val, cover_url, member_id)
        if read_date:
            db.add_past_cycle(conn, book_id, read_date)
    return go(f"/livros/{book_id}")


@app.get("/livros/{book_id}")
def book_detail(request: Request, book_id: int):
    with db.connect() as conn:
        book = db.get_book(conn, book_id)
        if not book or book["id"] is None:
            raise HTTPException(404, "Livro não encontrado.")
        return templates.TemplateResponse(
            request,
            "book.html",
            {
                "book": book,
                "reviews": db.reviews_for_book(conn, book_id),
                "members": db.list_members(conn),
            },
        )


@app.post("/livros/{book_id}/resenha")
def post_review(
    book_id: int,
    member_name: str = Form(...),
    rating: int = Form(...),
    text: str = Form(""),
):
    if not member_name.strip():
        raise HTTPException(400, "Informe seu nome.")
    if not 1 <= rating <= 5:
        raise HTTPException(400, "A nota deve ir de 1 a 5.")
    with db.connect() as conn:
        if not db.get_book(conn, book_id):
            raise HTTPException(404, "Livro não encontrado.")
        member_id = db.get_or_create_member(conn, member_name)
        db.upsert_review(conn, book_id, member_id, rating, text)
    return go(f"/livros/{book_id}")


@app.post("/livros/{book_id}/atual")
def make_current(book_id: int):
    with db.connect() as conn:
        if not db.get_book(conn, book_id):
            raise HTTPException(404, "Livro não encontrado.")
        db.set_current_book(conn, book_id)
    return go("/")


@app.post("/livros/{book_id}/passado")
def mark_past(book_id: int, read_on: str = Form("")):
    read_date = parse_read_on(read_on)
    with db.connect() as conn:
        if not db.get_book(conn, book_id):
            raise HTTPException(404, "Livro não encontrado.")
        db.add_past_cycle(conn, book_id, read_date)
    return go(f"/livros/{book_id}")


@app.post("/ciclo/encerrar")
def end_cycle():
    with db.connect() as conn:
        db.finish_current_cycle(conn)
    return go("/")


@app.get("/membros")
def members(request: Request):
    with db.connect() as conn:
        return templates.TemplateResponse(request, "members.html", {"members": db.list_members(conn)})


@app.get("/membros/{member_id}")
def member_detail(request: Request, member_id: int):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Membro não encontrado.")
        return templates.TemplateResponse(
            request, "member.html", {"member": row, "reviews": db.reviews_for_member(conn, member_id)}
        )


@app.get("/historico")
def history(request: Request):
    with db.connect() as conn:
        return templates.TemplateResponse(request, "history.html", {"cycles": db.list_cycles(conn)})
