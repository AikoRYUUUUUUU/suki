import os
import re
import sqlite3
import unicodedata

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "mangadb.db"))
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Cria as tabelas se ainda não existirem. Idempotente e seguro rodar sempre."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()
    conn = get_connection()
    conn.executescript(schema)
    conn.commit()
    conn.close()


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "manga"


def unique_slug(conn, base_slug):
    slug = base_slug
    n = 2
    while conn.execute("SELECT 1 FROM mangas WHERE id = ?", (slug,)).fetchone():
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


# ---------- leitura para dropdowns do admin ----------

def get_tags():
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM tags ORDER BY name")]
    conn.close()
    return rows


def get_authors():
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM authors ORDER BY name")]
    conn.close()
    return rows


def get_groups():
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM groups ORDER BY name")]
    conn.close()
    return rows


def get_dashboard_mangas():
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("""
        SELECT m.id, m.title, m.status, COUNT(c.id) AS chapter_count
        FROM mangas m
        LEFT JOIN chapters c ON c.manga_id = m.id
        GROUP BY m.id
        ORDER BY m.title
    """)]
    conn.close()
    return rows


def manga_exists(manga_id):
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM mangas WHERE id = ?", (manga_id,)).fetchone()
    conn.close()
    return row is not None


def get_manga_title(manga_id):
    conn = get_connection()
    row = conn.execute("SELECT title FROM mangas WHERE id = ?", (manga_id,)).fetchone()
    conn.close()
    return row["title"] if row else None


def next_chapter_number(manga_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(number) AS max_number FROM chapters WHERE manga_id = ?", (manga_id,)
    ).fetchone()
    conn.close()
    if row["max_number"] is None:
        return 1
    return row["max_number"] + 1


# ---------- leitura para a API pública (mesmo formato do antigo data/db.json) ----------

def static_url(path):
    """Assets como 'assets/covers/x.svg' são servidos por Flask em /static/.
    URLs absolutas (http/https) ou já prefixadas com / passam intactas."""
    if not path:
        return path
    if path.startswith(("http://", "https://", "/")):
        return path
    return f"/static/{path}"


def get_all_mangas_full():
    conn = get_connection()
    mangas = conn.execute("""
        SELECT m.*, a.name AS author_name, g.name AS group_name
        FROM mangas m
        LEFT JOIN authors a ON a.id = m.author_id
        LEFT JOIN groups g ON g.id = m.group_id
        ORDER BY m.title
    """).fetchall()

    result = []
    for m in mangas:
        genres = [r["name"] for r in conn.execute("""
            SELECT t.name FROM tags t
            JOIN manga_tags mt ON mt.tag_id = t.id
            WHERE mt.manga_id = ?
            ORDER BY t.name
        """, (m["id"],))]

        chapters = []
        for c in conn.execute(
            "SELECT * FROM chapters WHERE manga_id = ? ORDER BY number", (m["id"],)
        ):
            pages = [static_url(r["image_path"]) for r in conn.execute(
                "SELECT image_path FROM pages WHERE chapter_id = ? ORDER BY position",
                (c["id"],),
            )]
            chapters.append({
                "id": c["id"],
                "number": c["number"],
                "title": c["title"],
                "releaseDate": c["release_date"],
                "pages": pages,
            })

        result.append({
            "id": m["id"],
            "title": m["title"],
            "titleOriginal": m["title_original"],
            "author": m["author_name"],
            "artist": m["artist"],
            "group": m["group_name"],
            "status": m["status"],
            "year": m["year"],
            "genres": genres,
            "rating": m["rating"],
            "cover": static_url(m["cover"]),
            "synopsis": m["synopsis"],
            "chapters": chapters,
        })

    conn.close()
    return result


# ---------- escrita (admin) ----------

class ValidationError(Exception):
    pass


def add_manga(title, synopsis, status, tag_ids, author_id, group_id,
              title_original=None, artist=None, year=None, rating=None, cover=None):
    title = (title or "").strip()
    synopsis = (synopsis or "").strip()
    status = (status or "").strip()
    if not title:
        raise ValidationError("Título é obrigatório.")
    if not synopsis:
        raise ValidationError("Descrição é obrigatória.")
    if not status:
        raise ValidationError("Status é obrigatório.")

    year_val = None
    if year not in (None, ""):
        try:
            year_val = int(year)
        except (TypeError, ValueError):
            raise ValidationError("Ano inválido.")
        if year_val < 1900 or year_val > 2100:
            raise ValidationError("Ano fora da faixa permitida.")

    rating_val = None
    if rating not in (None, ""):
        try:
            rating_val = float(rating)
        except (TypeError, ValueError):
            raise ValidationError("Avaliação inválida.")
        if rating_val < 0 or rating_val > 5:
            raise ValidationError("Avaliação deve estar entre 0 e 5.")

    conn = get_connection()
    try:
        author_id_val = None
        if author_id not in (None, ""):
            author_id_val = int(author_id)
            if not conn.execute("SELECT 1 FROM authors WHERE id = ?", (author_id_val,)).fetchone():
                raise ValidationError("Autor inválido.")

        group_id_val = None
        if group_id not in (None, ""):
            group_id_val = int(group_id)
            if not conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id_val,)).fetchone():
                raise ValidationError("Grupo inválido.")

        clean_tag_ids = []
        for tid in (tag_ids or []):
            if tid in (None, ""):
                continue
            tid_val = int(tid)
            if not conn.execute("SELECT 1 FROM tags WHERE id = ?", (tid_val,)).fetchone():
                raise ValidationError("Tag inválida.")
            clean_tag_ids.append(tid_val)

        manga_id = unique_slug(conn, slugify(title))

        conn.execute("""
            INSERT INTO mangas (id, title, title_original, author_id, artist, group_id,
                                 status, year, rating, cover, synopsis)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (manga_id, title, title_original, author_id_val, artist, group_id_val,
              status, year_val, rating_val, cover, synopsis))

        for tid_val in clean_tag_ids:
            conn.execute(
                "INSERT INTO manga_tags (manga_id, tag_id) VALUES (?, ?)",
                (manga_id, tid_val),
            )

        conn.commit()
        return manga_id
    finally:
        conn.close()


def validate_chapter_fields(number, title):
    """Validação pura, sem tocar disco/banco - roda antes de qualquer upload de arquivo."""
    title = (title or "").strip()
    if not title:
        raise ValidationError("Título do capítulo é obrigatório.")

    if number in (None, ""):
        raise ValidationError("Número do capítulo é obrigatório.")
    try:
        number_val = float(number)
    except (TypeError, ValueError):
        raise ValidationError("Número do capítulo inválido.")
    if number_val <= 0:
        raise ValidationError("Número do capítulo deve ser positivo.")

    return number_val, title


def format_number(number_val):
    if number_val == int(number_val):
        return str(int(number_val))
    return str(number_val)


def _unique_chapter_slug(conn, manga_id, number_val):
    base = f"{manga_id}-cap-{slugify(format_number(number_val))}"
    slug = base
    n = 2
    while conn.execute("SELECT 1 FROM chapters WHERE id = ?", (slug,)).fetchone():
        slug = f"{base}-{n}"
        n += 1
    return slug


def build_chapter_id(manga_id, number_val):
    conn = get_connection()
    try:
        return _unique_chapter_slug(conn, manga_id, number_val)
    finally:
        conn.close()


def add_chapter(manga_id, chapter_id, number_val, title, release_date, page_paths):
    if not page_paths:
        raise ValidationError("Selecione ao menos uma imagem de página.")

    conn = get_connection()
    try:
        if not conn.execute("SELECT 1 FROM mangas WHERE id = ?", (manga_id,)).fetchone():
            raise ValidationError("Mangá inválido.")

        conn.execute("""
            INSERT INTO chapters (id, manga_id, number, title, release_date)
            VALUES (?, ?, ?, ?, ?)
        """, (chapter_id, manga_id, number_val, title, release_date or None))

        for position, path in enumerate(page_paths):
            conn.execute("""
                INSERT INTO pages (chapter_id, position, image_path)
                VALUES (?, ?, ?)
            """, (chapter_id, position, path))

        conn.commit()
    finally:
        conn.close()
