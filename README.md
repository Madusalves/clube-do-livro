# Clube do Livro

Um "Letterboxd de livros" para o clube: cada membro escreve resenhas e dá notas, e o clube marca qual livro está lendo. **Nenhum livro é hospedado**, só as opiniões.

Esta é a **Fase 1** do projeto: um app simples e utilizável. A Fase 2 em diante (grafo + GraphRAG) vai em cima destes dados.

## Funcionalidades

- Cadastro de livros (título, autor, ano, capa opcional, quem indicou)
- Resenhas com nota de 1 a 5 (uma por membro por livro; reenviar atualiza)
- Livro atual do clube e histórico de leituras (ciclos)
- Páginas de membros com suas resenhas
- Sem login: o membro informa o nome ao resenhar (ideal para um clube pequeno e de confiança)

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python seed.py                   # opcional: dados de exemplo
uvicorn app.main:app --reload
```

Abra http://127.0.0.1:8000. O banco é o arquivo `clube.db` (SQLite), criado automaticamente. Para usar outro caminho: `CLUBE_DB=/caminho/clube.db`.

## Testes

```bash
pytest
```

## Estrutura

```
app/
  main.py        rotas (FastAPI)
  db.py          acesso a dados (SQLite)
  templates/     páginas (Jinja2)
  static/        CSS
seed.py          dados de exemplo
tests/           testes das rotas
```

## Modelo de dados

`members` · `books` · `cycles` (período de leitura de um livro pelo clube) · `reviews` (membro + livro + nota + texto)

Este esquema já é, na prática, o grafo da próxima fase: Membro-ESCREVEU→Resenha-SOBRE→Livro, Livro-LIDO_EM→Ciclo.

## Próximos passos

1. Importar metadados e capas de uma API pública (Open Library) ao cadastrar o livro
2. Sincronizar os dados com o Neo4j
3. Extrair temas e aspectos das resenhas com um LLM
4. "Pergunte ao clube": comparar RAG vetorial com GraphRAG
