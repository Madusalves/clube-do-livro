"""Popula o banco com dados de exemplo (fictícios) para testar a interface.

Uso:  python seed.py
"""
from app import db

BOOKS = [
    ("Dom Casmurro", "Machado de Assis", 1899),
    ("Capitães da Areia", "Jorge Amado", 1937),
    ("A Hora da Estrela", "Clarice Lispector", 1977),
    ("Grande Sertão: Veredas", "João Guimarães Rosa", 1956),
]

REVIEWS = [
    ("Dom Casmurro", "Ana", 5, "Reli e ainda fico em dúvida sobre a Capitu. O narrador é o grande personagem."),
    ("Dom Casmurro", "Bruno", 3, "Bem escrito, mas achei o ritmo arrastado no meio."),
    ("Capitães da Areia", "Ana", 4, "Muito humano. As cenas do trapiche ficam na cabeça."),
    ("A Hora da Estrela", "Carla", 5, "Curto e devastador. A Macabéa é inesquecível."),
]


def main():
    db.init_db()
    with db.connect() as conn:
        ids = {}
        for title, author, year in BOOKS:
            ids[title] = db.add_book(conn, title, author, year)
        for title, member, rating, text in REVIEWS:
            member_id = db.get_or_create_member(conn, member)
            db.upsert_review(conn, ids[title], member_id, rating, text)
        db.set_current_book(conn, ids["Grande Sertão: Veredas"])
    print("Dados de exemplo criados.")


if __name__ == "__main__":
    main()
