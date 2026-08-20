import os
import re
import sqlite3
import unicodedata
from datetime import date

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "mangadb.db"))
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

MANGA_STATUSES = ["Em Hiatus", "Em andamento", "Finalizado"]

# Catálogo fixo de tags (substitui a entrada manual no admin). Agrupado pra exibição
# em seções no admin e no filtro de busca; "Conteúdo sensível" leva aviso na UI.
TAG_GROUPS = {
    "Gêneros": [
        "Ação", "Aventura", "Comédia", "Drama", "Fantasia", "Ficção Científica",
        "Terror", "Mistério", "Suspense", "Romance", "Slice of Life", "Sobrenatural",
        "Psicológico", "Esporte", "Histórico", "Mecha", "Isekai", "Escolar",
    ],
    "Demografia": ["Shounen", "Shoujo", "Seinen", "Josei"],
    "Relacionamento": ["Yaoi", "Yuri", "Harém"],
    "Conteúdo sensível": ["Ecchi", "Smut", "Hentai", "Adulto (18+)", "Mature"],
}
FIXED_TAGS = [tag for tags in TAG_GROUPS.values() for tag in tags]
SENSITIVE_TAGS = set(TAG_GROUPS["Conteúdo sensível"])


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


def get_manga_chapters(manga_id):
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("""
        SELECT c.id, c.number, c.title, c.release_date, COUNT(p.id) AS page_count
        FROM chapters c
        LEFT JOIN pages p ON p.chapter_id = c.id
        WHERE c.manga_id = ?
        GROUP BY c.id
        ORDER BY c.number
    """, (manga_id,))]
    conn.close()
    return rows


def get_or_create_tag(conn, name):
    """Opera na conexão do chamador (nunca abre a própria) - assim fica dentro da mesma
    transação de quem está inserindo o mangá, evitando lock de escritor concorrente do
    SQLite entre duas conexões abertas ao mesmo tempo."""
    name = name.strip()
    row = conn.execute("SELECT id FROM tags WHERE lower(name) = lower(?)", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    return cur.lastrowid


def get_or_create_author(conn, name):
    name = name.strip()
    row = conn.execute("SELECT id FROM authors WHERE lower(name) = lower(?)", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO authors (name) VALUES (?)", (name,))
    return cur.lastrowid


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


def validate_manga_fields(title, synopsis, status, tags, author, group_id, year=None, rating=None):
    """Validação pura (só leitura, sem criar nada) - reaproveitada por add_manga e pela
    rota de preview em app.py, pra não duplicar regra entre as duas. Tags e autor são
    texto livre (get-or-create acontece só na hora de gravar, em add_manga)."""
    title = (title or "").strip()
    synopsis = (synopsis or "").strip()
    status = (status or "").strip()
    author = (author or "").strip()
    if not title:
        raise ValidationError("Título é obrigatório.")
    if not synopsis:
        raise ValidationError("Descrição é obrigatória.")
    if not status:
        raise ValidationError("Status é obrigatório.")
    if status not in MANGA_STATUSES:
        raise ValidationError("Status inválido.")

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

    seen = set()
    tag_names = []
    for raw in (tags or "").split(","):
        name = raw.strip()
        if not name or name.lower() in seen:
            continue
        if name not in FIXED_TAGS:
            raise ValidationError(f"Tag inválida: {name}")
        seen.add(name.lower())
        tag_names.append(name)

    conn = get_connection()
    try:
        group_id_val = None
        if group_id not in (None, ""):
            group_id_val = int(group_id)
            if not conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id_val,)).fetchone():
                raise ValidationError("Grupo inválido.")
    finally:
        conn.close()

    return {
        "title": title, "synopsis": synopsis, "status": status,
        "year": year_val, "rating": rating_val,
        "author": author, "group_id": group_id_val,
        "tag_names": tag_names,
    }


def add_manga(title, synopsis, status, tags, author, group_id,
              title_original=None, artist=None, year=None, rating=None, cover=None):
    f = validate_manga_fields(title, synopsis, status, tags, author, group_id, year, rating)

    conn = get_connection()
    try:
        manga_id = unique_slug(conn, slugify(f["title"]))

        author_id_val = get_or_create_author(conn, f["author"]) if f["author"] else None

        conn.execute("""
            INSERT INTO mangas (id, title, title_original, author_id, artist, group_id,
                                 status, year, rating, cover, synopsis)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (manga_id, f["title"], title_original, author_id_val, artist, f["group_id"],
              f["status"], f["year"], f["rating"], cover, f["synopsis"]))

        for name in f["tag_names"]:
            tag_id = get_or_create_tag(conn, name)
            conn.execute(
                "INSERT INTO manga_tags (manga_id, tag_id) VALUES (?, ?)",
                (manga_id, tag_id),
            )

        conn.commit()
        return manga_id
    finally:
        conn.close()


def get_manga_cover(manga_id):
    conn = get_connection()
    row = conn.execute("SELECT cover FROM mangas WHERE id = ?", (manga_id,)).fetchone()
    conn.close()
    return row["cover"] if row else None


def update_manga_cover(manga_id, cover_path):
    conn = get_connection()
    conn.execute("UPDATE mangas SET cover = ? WHERE id = ?", (cover_path, manga_id))
    conn.commit()
    conn.close()


def update_manga_status(manga_id, status):
    conn = get_connection()
    conn.execute("UPDATE mangas SET status = ? WHERE id = ?", (status, manga_id))
    conn.commit()
    conn.close()


def get_manga_pages_with_paths(manga_id):
    """Todas as páginas (de todos os capítulos) desse mangá - usado pra saber o que
    limpar do disco antes de apagar o mangá (o cascade do SQLite só cuida do banco)."""
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("""
        SELECT p.id, p.image_path FROM pages p
        JOIN chapters c ON c.id = p.chapter_id
        WHERE c.manga_id = ?
    """, (manga_id,))]
    conn.close()
    return rows


def delete_manga(manga_id):
    conn = get_connection()
    conn.execute("DELETE FROM mangas WHERE id = ?", (manga_id,))
    conn.commit()
    conn.close()


def delete_chapter(chapter_id):
    conn = get_connection()
    conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
    conn.commit()
    conn.close()


def validate_chapter_fields(number, title, release_date, manga_id, exclude_chapter_id=None):
    """Validação pura, sem tocar disco - roda antes de qualquer upload de arquivo.
    `exclude_chapter_id` é usado na edição, pra não comparar o capítulo com ele mesmo
    na checagem de número duplicado."""
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

    release_date = (release_date or "").strip()
    if not release_date:
        raise ValidationError("Data de publicação é obrigatória.")
    try:
        date.fromisoformat(release_date)
    except ValueError:
        raise ValidationError("Data de publicação inválida.")

    conn = get_connection()
    try:
        query = "SELECT 1 FROM chapters WHERE manga_id = ? AND number = ?"
        params = [manga_id, number_val]
        if exclude_chapter_id is not None:
            query += " AND id != ?"
            params.append(exclude_chapter_id)
        if conn.execute(query, params).fetchone():
            raise ValidationError(f"Já existe um capítulo {format_number(number_val)} nesse mangá.")
    finally:
        conn.close()

    return number_val, title, release_date


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


# ---------- edição de capítulo existente ----------

def get_chapter_edit_data(manga_id, chapter_id):
    """Devolve os metadados do capítulo + páginas (ordenadas) se ele pertence a esse
    mangá, ou None se não existir/pertencer a outro mangá."""
    conn = get_connection()
    try:
        chapter = conn.execute(
            "SELECT * FROM chapters WHERE id = ? AND manga_id = ?", (chapter_id, manga_id)
        ).fetchone()
        if not chapter:
            return None
        pages = [dict(r) for r in conn.execute(
            "SELECT id, position, image_path FROM pages WHERE chapter_id = ? ORDER BY position",
            (chapter_id,),
        )]
        return {
            "id": chapter["id"], "number": chapter["number"], "title": chapter["title"],
            "release_date": chapter["release_date"], "pages": pages,
        }
    finally:
        conn.close()


def update_chapter_metadata(chapter_id, number_val, title, release_date):
    conn = get_connection()
    conn.execute(
        "UPDATE chapters SET number = ?, title = ?, release_date = ? WHERE id = ?",
        (number_val, title, release_date, chapter_id),
    )
    conn.commit()
    conn.close()


def get_pages_by_ids(page_ids):
    if not page_ids:
        return []
    conn = get_connection()
    placeholders = ",".join("?" for _ in page_ids)
    rows = [dict(r) for r in conn.execute(
        f"SELECT id, position, image_path FROM pages WHERE id IN ({placeholders})", page_ids
    )]
    conn.close()
    return rows


def count_pages_with_image_path(image_path, exclude_ids=()):
    """Quantas linhas de `pages` apontam pra esse mesmo arquivo, ignorando as linhas em
    `exclude_ids`. Usado antes de apagar um arquivo do disco - se alguma outra página
    (fora do lote que está sendo apagado agora) ainda usa o mesmo caminho (pode
    acontecer com dados de seed/demo reaproveitando imagens), o arquivo não pode ser
    apagado. `exclude_ids` deve ser o conjunto de páginas do próprio lote sendo
    excluído - sem isso, apagar várias páginas que compartilham arquivo de uma vez
    (ex.: excluir o mangá inteiro) faria cada uma "ver" a outra como ainda em uso e
    nenhuma seria apagada, deixando lixo órfão no disco."""
    conn = get_connection()
    if exclude_ids:
        placeholders = ",".join("?" for _ in exclude_ids)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM pages WHERE image_path = ? AND id NOT IN ({placeholders})",
            [image_path, *exclude_ids],
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM pages WHERE image_path = ?", (image_path,)
        ).fetchone()
    conn.close()
    return row["n"]


def delete_pages_by_ids(page_ids):
    if not page_ids:
        return
    conn = get_connection()
    placeholders = ",".join("?" for _ in page_ids)
    conn.execute(f"DELETE FROM pages WHERE id IN ({placeholders})", page_ids)
    conn.commit()
    conn.close()


def set_page_position(page_id, position):
    conn = get_connection()
    conn.execute("UPDATE pages SET position = ? WHERE id = ?", (position, page_id))
    conn.commit()
    conn.close()


def insert_page(chapter_id, position, image_path):
    conn = get_connection()
    conn.execute(
        "INSERT INTO pages (chapter_id, position, image_path) VALUES (?, ?, ?)",
        (chapter_id, position, image_path),
    )
    conn.commit()
    conn.close()
