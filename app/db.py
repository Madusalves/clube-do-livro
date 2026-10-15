"""Camada de dados (SQLite). Fonte de verdade do app; o grafo (Neo4j) virá depois, sincronizado daqui."""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("CLUBE_DB", os.path.join(os.path.dirname(__file__), "..", "clube.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    year INTEGER,
    cover_url TEXT,
    suggested_by INTEGER REFERENCES members(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(title, author)
);

-- Um ciclo = período em que o clube lê um livro. No máximo um ciclo "atual" (finished_at IS NULL).
CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    started_at TEXT NOT NULL DEFAULT CURRENT_DATE,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    member_id INTEGER NOT NULL REFERENCES members(id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(book_id, member_id)
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


# ---------- membros ----------

def get_or_create_member(conn, name: str) -> int:
    name = name.strip()
    row = conn.execute("SELECT id FROM members WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if row:
        return row["id"]
    return conn.execute("INSERT INTO members (name) VALUES (?)", (name,)).lastrowid


def list_members(conn):
    return conn.execute(
        """SELECT m.id, m.name, COUNT(r.id) AS n_reviews, ROUND(AVG(r.rating), 1) AS avg_rating
           FROM members m LEFT JOIN reviews r ON r.member_id = m.id
           GROUP BY m.id ORDER BY m.name"""
    ).fetchall()


# ---------- livros ----------

def add_book(conn, title, author, year=None, cover_url=None, suggested_by=None) -> int:
    row = conn.execute(
        "SELECT id FROM books WHERE title = ? COLLATE NOCASE AND author = ? COLLATE NOCASE",
        (title.strip(), author.strip()),
    ).fetchone()
    if row:
        return row["id"]
    return conn.execute(
        "INSERT INTO books (title, author, year, cover_url, suggested_by) VALUES (?, ?, ?, ?, ?)",
        (title.strip(), author.strip(), year, cover_url or None, suggested_by),
    ).lastrowid


def list_books(conn):
    return conn.execute(
        """SELECT b.*, COUNT(r.id) AS n_reviews, ROUND(AVG(r.rating), 1) AS avg_rating,
                  EXISTS(SELECT 1 FROM cycles c WHERE c.book_id = b.id AND c.finished_at IS NULL) AS is_current
           FROM books b LEFT JOIN reviews r ON r.book_id = b.id
           GROUP BY b.id ORDER BY b.created_at DESC, b.id DESC"""
    ).fetchall()


def search_books(conn, query: str):
    like = f"%{query.strip()}%"
    return conn.execute(
        """SELECT b.*, COUNT(r.id) AS n_reviews, ROUND(AVG(r.rating), 1) AS avg_rating
           FROM books b LEFT JOIN reviews r ON r.book_id = b.id
           WHERE b.title LIKE ? OR b.author LIKE ?
           GROUP BY b.id ORDER BY n_reviews DESC, b.title""",
        (like, like),
    ).fetchall()


def get_book(conn, book_id: int):
    return conn.execute(
        """SELECT b.*, m.name AS suggested_by_name,
                  COUNT(r.id) AS n_reviews, ROUND(AVG(r.rating), 1) AS avg_rating,
                  EXISTS(SELECT 1 FROM cycles c WHERE c.book_id = b.id AND c.finished_at IS NULL) AS is_current
           FROM books b
           LEFT JOIN members m ON m.id = b.suggested_by
           LEFT JOIN reviews r ON r.book_id = b.id
           WHERE b.id = ? GROUP BY b.id""",
        (book_id,),
    ).fetchone()


# ---------- ciclos ----------

def current_cycle(conn):
    return conn.execute(
        """SELECT c.*, b.title, b.author, b.year, b.cover_url
           FROM cycles c JOIN books b ON b.id = c.book_id
           WHERE c.finished_at IS NULL ORDER BY c.id DESC LIMIT 1"""
    ).fetchone()


def set_current_book(conn, book_id: int):
    """Encerra o ciclo atual (se houver) e abre um novo para o livro informado."""
    cur = current_cycle(conn)
    if cur and cur["book_id"] == book_id:
        return
    conn.execute("UPDATE cycles SET finished_at = CURRENT_DATE WHERE finished_at IS NULL")
    conn.execute("INSERT INTO cycles (book_id) VALUES (?)", (book_id,))


def finish_current_cycle(conn):
    conn.execute("UPDATE cycles SET finished_at = CURRENT_DATE WHERE finished_at IS NULL")


def list_cycles(conn):
    return conn.execute(
        """SELECT c.*, b.title, b.author,
                  (SELECT ROUND(AVG(rating), 1) FROM reviews r WHERE r.book_id = b.id) AS avg_rating,
                  (SELECT COUNT(*) FROM reviews r WHERE r.book_id = b.id) AS n_reviews
           FROM cycles c JOIN books b ON b.id = c.book_id
           ORDER BY c.id DESC"""
    ).fetchall()


# ---------- resenhas ----------

def upsert_review(conn, book_id: int, member_id: int, rating: int, text: str):
    conn.execute(
        """INSERT INTO reviews (book_id, member_id, rating, text) VALUES (?, ?, ?, ?)
           ON CONFLICT(book_id, member_id)
           DO UPDATE SET rating = excluded.rating, text = excluded.text, created_at = CURRENT_TIMESTAMP""",
        (book_id, member_id, rating, text.strip()),
    )


def reviews_for_book(conn, book_id: int):
    return conn.execute(
        """SELECT r.*, m.name AS member_name FROM reviews r
           JOIN members m ON m.id = r.member_id
           WHERE r.book_id = ? ORDER BY r.created_at DESC""",
        (book_id,),
    ).fetchall()


def recent_reviews(conn, limit=8):
    return conn.execute(
        """SELECT r.*, m.name AS member_name, b.title AS book_title, b.id AS book_id
           FROM reviews r JOIN members m ON m.id = r.member_id JOIN books b ON b.id = r.book_id
           ORDER BY r.created_at DESC, r.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def reviews_for_member(conn, member_id: int):
    return conn.execute(
        """SELECT r.*, b.title AS book_title, b.author AS book_author FROM reviews r
           JOIN books b ON b.id = r.book_id WHERE r.member_id = ? ORDER BY r.created_at DESC""",
        (member_id,),
    ).fetchall()
