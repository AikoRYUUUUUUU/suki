import os
import re
import sqlite3
import unicodedata
from datetime import date, datetime

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
    "Formato": ["Mangá", "Manhua", "Manhwa", "Webtoon"],
    "Demografia": ["Shounen", "Shoujo", "Seinen", "Josei"],
    "Relacionamento": ["Yaoi", "Yuri", "Harém"],
    "Conteúdo sensível": ["Ecchi", "Smut", "Adulto (18+)", "Mature"],
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
    _migrate_pages_size_bytes(conn)
    _migrate_mangas_rating_votes(conn)
    _migrate_remove_hentai_tag(conn)
    _migrate_mangas_discord_role(conn)
    conn.commit()
    conn.close()


def _migrate_pages_size_bytes(conn):
    """`CREATE TABLE IF NOT EXISTS` não altera uma tabela `pages` já existente
    (banco de produção criado antes da coluna `size_bytes` existir) - então essa
    migração roda toda vez que o app sobe (idempotente, barata) e adiciona a
    coluna se ainda não estiver lá."""
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(pages)")]
    if "size_bytes" not in columns:
        conn.execute("ALTER TABLE pages ADD COLUMN size_bytes INTEGER")


def _migrate_mangas_rating_votes(conn):
    """Mesmo princípio: adiciona rating_sum/rating_count numa tabela `mangas` já
    existente (banco de produção criado antes do sistema de votos)."""
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(mangas)")]
    if "rating_sum" not in columns:
        conn.execute("ALTER TABLE mangas ADD COLUMN rating_sum REAL NOT NULL DEFAULT 0")
    if "rating_count" not in columns:
        conn.execute("ALTER TABLE mangas ADD COLUMN rating_count INTEGER NOT NULL DEFAULT 0")


def _migrate_remove_hentai_tag(conn):
    """A tag "Hentai" foi retirada do site (não faz mais parte de TAG_GROUPS) -
    remove qualquer linha remanescente de um banco de produção onde ela já
    tenha sido criada/associada. `ON DELETE CASCADE` em manga_tags.tag_id
    limpa as associações junto."""
    conn.execute("DELETE FROM tags WHERE lower(name) = 'hentai'")


def _migrate_mangas_discord_role(conn):
    """Cargo do Discord criado pelo bot pra esse mangá (leitor segue só as séries
    que quiser) - coluna nova numa tabela `mangas` já existente."""
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(mangas)")]
    if "discord_role_id" not in columns:
        conn.execute("ALTER TABLE mangas ADD COLUMN discord_role_id TEXT")


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
    """Subqueries em vez de dois LEFT JOIN (capítulos + comentários) na mesma
    query - joinar duas relações um-pra-muitos ao mesmo tempo multiplicaria as
    linhas (produto cartesiano) e inflaria os dois COUNT()."""
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("""
        SELECT m.id, m.title, m.status, m.cover,
            (SELECT COUNT(*) FROM chapters c WHERE c.manga_id = m.id) AS chapter_count,
            (SELECT COUNT(*) FROM comments cm WHERE cm.manga_id = m.id) AS comment_count
        FROM mangas m
        ORDER BY m.title
    """)]
    conn.close()
    for row in rows:
        row["cover"] = static_url(row["cover"])
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


def get_manga_synopsis(manga_id):
    conn = get_connection()
    row = conn.execute("SELECT synopsis FROM mangas WHERE id = ?", (manga_id,)).fetchone()
    conn.close()
    return row["synopsis"] if row else None


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


def get_all_manga_ids():
    """Só os ids, pra montar o sitemap sem puxar o catálogo inteiro."""
    conn = get_connection()
    rows = [r["id"] for r in conn.execute("SELECT id FROM mangas ORDER BY id")]
    conn.close()
    return rows


def search_mangas_by_title(query, limit=5):
    conn = get_connection()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, title, synopsis, cover FROM mangas WHERE title LIKE ? ORDER BY title LIMIT ?",
        (f"%{query}%", limit),
    )]
    conn.close()
    for row in rows:
        row["cover"] = static_url(row["cover"])
    return rows


def get_random_manga():
    conn = get_connection()
    row = conn.execute("SELECT id, title, synopsis, cover FROM mangas ORDER BY RANDOM() LIMIT 1").fetchone()
    conn.close()
    if not row:
        return None
    manga = dict(row)
    manga["cover"] = static_url(manga["cover"])
    return manga


def get_manga_public(manga_id):
    """Dados de um único mangá pra renderização server-side (título, sinopse, capa,
    gêneros...) - usada pra montar <title>/meta/OG antes do JS assumir a página,
    já que crawler de rede social (Discord, WhatsApp, Twitter) não executa JS."""
    conn = get_connection()
    m = conn.execute("""
        SELECT mg.*, a.name AS author_name
        FROM mangas mg
        LEFT JOIN authors a ON a.id = mg.author_id
        WHERE mg.id = ?
    """, (manga_id,)).fetchone()
    if not m:
        conn.close()
        return None

    genres = [r["name"] for r in conn.execute("""
        SELECT t.name FROM tags t
        JOIN manga_tags mt ON mt.tag_id = t.id
        WHERE mt.manga_id = ?
        ORDER BY t.name
    """, (manga_id,))]

    chapter_count = conn.execute(
        "SELECT COUNT(*) AS n FROM chapters WHERE manga_id = ?", (manga_id,)
    ).fetchone()["n"]

    conn.close()
    return {
        "id": m["id"],
        "title": m["title"],
        "titleOriginal": m["title_original"],
        "author": m["author_name"],
        "status": m["status"],
        "year": m["year"],
        "genres": genres,
        "rating": effective_rating(m),
        "ratingCount": m["rating_count"],
        "cover": static_url(m["cover"]),
        "synopsis": m["synopsis"],
        "chapterCount": chapter_count,
    }


def get_chapter_public(manga_id, chapter_id):
    """Título/capa do mangá + número/título do capítulo, pra meta/OG da página do leitor."""
    conn = get_connection()
    m = conn.execute(
        "SELECT title, cover FROM mangas WHERE id = ?", (manga_id,)
    ).fetchone()
    c = conn.execute(
        "SELECT number, title FROM chapters WHERE id = ? AND manga_id = ?",
        (chapter_id, manga_id),
    ).fetchone()
    conn.close()
    if not m or not c:
        return None
    return {
        "mangaTitle": m["title"],
        "cover": static_url(m["cover"]),
        "number": c["number"],
        "title": c["title"],
    }


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


def effective_rating(row):
    """Média dos votos dos leitores se já existir algum; senão cai pra nota fixa
    digitada pelo admin no cadastro (serve de valor inicial pra mangás sem voto ainda)."""
    if row["rating_count"]:
        return round(row["rating_sum"] / row["rating_count"], 2)
    return row["rating"]


def get_all_mangas_full():
    """Monta o catálogo inteiro em 4 queries fixas (independente de quantos mangás/
    capítulos existirem), em vez de uma query de gêneros e uma de capítulos por manga
    mais uma de páginas por capítulo - isso ficava mais lento a cada título novo."""
    conn = get_connection()
    mangas = conn.execute("""
        SELECT m.*, a.name AS author_name, g.name AS group_name
        FROM mangas m
        LEFT JOIN authors a ON a.id = m.author_id
        LEFT JOIN groups g ON g.id = m.group_id
        ORDER BY m.title
    """).fetchall()

    genres_by_manga = {}
    for r in conn.execute("""
        SELECT mt.manga_id, t.name FROM tags t
        JOIN manga_tags mt ON mt.tag_id = t.id
        ORDER BY t.name
    """):
        genres_by_manga.setdefault(r["manga_id"], []).append(r["name"])

    pages_by_chapter = {}
    for r in conn.execute("SELECT chapter_id, image_path FROM pages ORDER BY chapter_id, position"):
        pages_by_chapter.setdefault(r["chapter_id"], []).append(static_url(r["image_path"]))

    chapters_by_manga = {}
    for c in conn.execute("SELECT * FROM chapters ORDER BY manga_id, number"):
        chapters_by_manga.setdefault(c["manga_id"], []).append({
            "id": c["id"],
            "number": c["number"],
            "title": c["title"],
            "releaseDate": c["release_date"],
            "pages": pages_by_chapter.get(c["id"], []),
        })

    result = []
    for m in mangas:
        result.append({
            "id": m["id"],
            "title": m["title"],
            "titleOriginal": m["title_original"],
            "author": m["author_name"],
            "artist": m["artist"],
            "group": m["group_name"],
            "status": m["status"],
            "year": m["year"],
            "genres": genres_by_manga.get(m["id"], []),
            "rating": effective_rating(m),
            "ratingCount": m["rating_count"],
            "cover": static_url(m["cover"]),
            "synopsis": m["synopsis"],
            "chapters": chapters_by_manga.get(m["id"], []),
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


def get_manga_discord_role(manga_id):
    conn = get_connection()
    row = conn.execute("SELECT discord_role_id FROM mangas WHERE id = ?", (manga_id,)).fetchone()
    conn.close()
    return row["discord_role_id"] if row else None


def set_manga_discord_role(manga_id, role_id):
    conn = get_connection()
    conn.execute("UPDATE mangas SET discord_role_id = ? WHERE id = ?", (role_id, manga_id))
    conn.commit()
    conn.close()


def get_mangas_without_discord_role():
    conn = get_connection()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, title FROM mangas WHERE discord_role_id IS NULL ORDER BY title"
    )]
    conn.close()
    return rows


def get_mangas_with_discord_role():
    conn = get_connection()
    placeholders = ",".join("?" * len(SENSITIVE_TAGS))
    rows = [dict(r) for r in conn.execute(f"""
        SELECT m.title, m.discord_role_id,
            EXISTS(
                SELECT 1 FROM manga_tags mt
                JOIN tags t ON t.id = mt.tag_id
                WHERE mt.manga_id = m.id AND t.name IN ({placeholders})
            ) AS is_sensitive
        FROM mangas m
        WHERE m.discord_role_id IS NOT NULL
        ORDER BY m.title
    """, tuple(SENSITIVE_TAGS))]
    conn.close()
    return rows


def update_manga_status(manga_id, status):
    conn = get_connection()
    conn.execute("UPDATE mangas SET status = ? WHERE id = ?", (status, manga_id))
    conn.commit()
    conn.close()


def get_manga_edit_data(manga_id):
    conn = get_connection()
    row = conn.execute("""
        SELECT m.*, a.name AS author_name
        FROM mangas m
        LEFT JOIN authors a ON a.id = m.author_id
        WHERE m.id = ?
    """, (manga_id,)).fetchone()
    if not row:
        conn.close()
        return None
    tag_names = [r["name"] for r in conn.execute("""
        SELECT t.name FROM tags t
        JOIN manga_tags mt ON mt.tag_id = t.id
        WHERE mt.manga_id = ?
        ORDER BY t.name
    """, (manga_id,))]
    conn.close()
    return {
        "id": row["id"], "title": row["title"], "title_original": row["title_original"],
        "author_name": row["author_name"], "artist": row["artist"], "group_id": row["group_id"],
        "status": row["status"], "year": row["year"], "rating": row["rating"],
        "cover": static_url(row["cover"]), "synopsis": row["synopsis"], "tag_names": tag_names,
    }


def update_manga(manga_id, title, synopsis, status, tags, author, group_id,
                  title_original=None, artist=None, year=None, rating=None):
    f = validate_manga_fields(title, synopsis, status, tags, author, group_id, year, rating)

    conn = get_connection()
    try:
        author_id_val = get_or_create_author(conn, f["author"]) if f["author"] else None

        conn.execute("""
            UPDATE mangas SET title = ?, title_original = ?, author_id = ?, artist = ?,
                               group_id = ?, status = ?, year = ?, rating = ?, synopsis = ?
            WHERE id = ?
        """, (f["title"], title_original, author_id_val, artist, f["group_id"],
              f["status"], f["year"], f["rating"], f["synopsis"], manga_id))

        conn.execute("DELETE FROM manga_tags WHERE manga_id = ?", (manga_id,))
        for name in f["tag_names"]:
            tag_id = get_or_create_tag(conn, name)
            conn.execute(
                "INSERT INTO manga_tags (manga_id, tag_id) VALUES (?, ?)",
                (manga_id, tag_id),
            )

        conn.commit()
    finally:
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


def add_chapter(manga_id, chapter_id, number_val, title, release_date, pages):
    """`pages` é uma lista de (image_path, size_bytes)."""
    if not pages:
        raise ValidationError("Selecione ao menos uma imagem de página.")

    conn = get_connection()
    try:
        if not conn.execute("SELECT 1 FROM mangas WHERE id = ?", (manga_id,)).fetchone():
            raise ValidationError("Mangá inválido.")

        conn.execute("""
            INSERT INTO chapters (id, manga_id, number, title, release_date)
            VALUES (?, ?, ?, ?, ?)
        """, (chapter_id, manga_id, number_val, title, release_date or None))

        for position, (path, size_bytes) in enumerate(pages):
            conn.execute("""
                INSERT INTO pages (chapter_id, position, image_path, size_bytes)
                VALUES (?, ?, ?, ?)
            """, (chapter_id, position, path, size_bytes))

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


def insert_page(chapter_id, position, image_path, size_bytes=None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO pages (chapter_id, position, image_path, size_bytes) VALUES (?, ?, ?, ?)",
        (chapter_id, position, image_path, size_bytes),
    )
    conn.commit()
    conn.close()


# ---------- migração de imagens locais legadas pro R2 ----------

def get_migration_candidates():
    """Capas e páginas cujo caminho ainda é local (não começa com http/https) -
    tudo que foi enviado antes da migração pro R2 e ainda não foi movido."""
    conn = get_connection()
    covers = [dict(r) for r in conn.execute("""
        SELECT id AS manga_id, title, cover AS path FROM mangas
        WHERE cover IS NOT NULL AND cover NOT LIKE 'http%'
    """)]
    pages = [dict(r) for r in conn.execute("""
        SELECT p.id AS page_id, c.manga_id AS manga_id, p.image_path AS path
        FROM pages p JOIN chapters c ON c.id = p.chapter_id
        WHERE p.image_path NOT LIKE 'http%'
        ORDER BY c.manga_id, p.chapter_id, p.position
    """)]
    conn.close()
    return {"covers": covers, "pages": pages}


def get_page_by_id(page_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT p.id, p.image_path, c.manga_id FROM pages p "
        "JOIN chapters c ON c.id = p.chapter_id WHERE p.id = ?",
        (page_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_page_image(page_id, image_path, size_bytes):
    conn = get_connection()
    conn.execute(
        "UPDATE pages SET image_path = ?, size_bytes = ? WHERE id = ?",
        (image_path, size_bytes, page_id),
    )
    conn.commit()
    conn.close()


# ---------- avaliação dos leitores ----------

def add_vote(manga_id, voter_hash, value):
    """Registra o voto e atualiza a média numa única transação. A chave primária
    composta (manga_id, voter_hash) de `votes` é quem impede voto duplicado -
    o INSERT levanta sqlite3.IntegrityError se essa pessoa já votou nesse mangá
    (deixa o chamador decidir como responder, não trata aqui)."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO votes (manga_id, voter_hash, value) VALUES (?, ?, ?)",
            (manga_id, voter_hash, value),
        )
        conn.execute(
            "UPDATE mangas SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE id = ?",
            (value, manga_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT rating, rating_sum, rating_count FROM mangas WHERE id = ?", (manga_id,)
        ).fetchone()
    finally:
        conn.close()

    return effective_rating(row), row["rating_count"]


# ---------- comentários nativos ----------

def add_comment(manga_id, parent_id, author_name, body):
    """Publica na hora, sem fila de aprovação. Resposta a uma resposta é
    achatada pro comentário raiz (parent_id do pai, se ele tiver um) - assim a
    thread nunca passa de 2 níveis, o que casa com o que a UI mostra."""
    conn = get_connection()
    try:
        if parent_id:
            parent = conn.execute(
                "SELECT id, parent_id FROM comments WHERE id = ? AND manga_id = ?",
                (parent_id, manga_id),
            ).fetchone()
            if parent is None:
                parent_id = None
            elif parent["parent_id"]:
                parent_id = parent["parent_id"]

        cur = conn.execute(
            "INSERT INTO comments (manga_id, parent_id, author_name, body, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (manga_id, parent_id, author_name, body, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_comments(manga_id):
    """Monta a árvore (raízes com `replies`) em Python a partir de uma única
    query - o volume por mangá é pequeno o bastante pra isso ser mais simples
    que uma query recursiva, sem trade-off de performance real."""
    conn = get_connection()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, parent_id, author_name, body, created_at, score "
        "FROM comments WHERE manga_id = ?",
        (manga_id,),
    )]
    conn.close()

    by_id = {r["id"]: {**r, "replies": []} for r in rows}
    top_level = []
    for r in rows:
        node = by_id[r["id"]]
        if r["parent_id"] and r["parent_id"] in by_id:
            by_id[r["parent_id"]]["replies"].append(node)
        else:
            top_level.append(node)

    top_level.sort(key=lambda c: (-c["score"], c["created_at"]))
    for node in by_id.values():
        node["replies"].sort(key=lambda c: c["created_at"])

    return top_level


def comment_exists(comment_id):
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM comments WHERE id = ?", (comment_id,)).fetchone()
    conn.close()
    return row is not None


def vote_comment(comment_id, voter_hash, value):
    """Mesmo desenho de add_vote() pra avaliação de mangá: chave composta em
    comment_votes barra voto duplicado (levanta IntegrityError, quem chama
    decide como responder), score fica cacheado em comments.score."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO comment_votes (comment_id, voter_hash, value) VALUES (?, ?, ?)",
            (comment_id, voter_hash, value),
        )
        conn.execute(
            "UPDATE comments SET score = score + ? WHERE id = ?",
            (value, comment_id),
        )
        conn.commit()
        row = conn.execute("SELECT score FROM comments WHERE id = ?", (comment_id,)).fetchone()
    finally:
        conn.close()
    return row["score"]


def delete_comment(manga_id, comment_id):
    """ON DELETE CASCADE cuida das respostas (parent_id) e dos votos junto.
    Exige manga_id pra garantir que o admin só apaga comentários do mangá que
    está de fato vendo, mesmo que o comment_id na URL seja adulterado."""
    conn = get_connection()
    conn.execute("DELETE FROM comments WHERE id = ? AND manga_id = ?", (comment_id, manga_id))
    conn.commit()
    conn.close()
