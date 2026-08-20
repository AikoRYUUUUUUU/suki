-- Schema do banco de dados do Suki. Versionado no git; o arquivo .db real
-- (com os dados) nunca é commitado — veja .gitignore.

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS mangas (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    title_original TEXT,
    author_id INTEGER REFERENCES authors(id),
    artist TEXT,
    group_id INTEGER REFERENCES groups(id),
    status TEXT NOT NULL,
    year INTEGER,
    rating REAL,
    cover TEXT,
    synopsis TEXT NOT NULL,
    rating_sum REAL NOT NULL DEFAULT 0,
    rating_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS manga_tags (
    manga_id TEXT NOT NULL REFERENCES mangas(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (manga_id, tag_id)
);

CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY,
    manga_id TEXT NOT NULL REFERENCES mangas(id) ON DELETE CASCADE,
    number REAL NOT NULL,
    title TEXT NOT NULL,
    release_date TEXT
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    size_bytes INTEGER
);

-- Um voto por (mangá, impressão digital do leitor) - a chave primária composta
-- é o que impede voto duplicado, sem precisar de conta de usuário.
CREATE TABLE IF NOT EXISTS votes (
    manga_id TEXT NOT NULL REFERENCES mangas(id) ON DELETE CASCADE,
    voter_hash TEXT NOT NULL,
    value INTEGER NOT NULL,
    PRIMARY KEY (manga_id, voter_hash)
);

-- Fila de aprovação automática de comentários do Cusdis: o webhook deles chega
-- aqui (entrada, sem custo de saída bloqueada pelo free-tier), fica guardado
-- até o navegador do admin (a próxima vez que o painel carregar) buscar essa
-- fila e clicar o approve_link de cada um sozinho.
CREATE TABLE IF NOT EXISTS pending_comment_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    approve_link TEXT NOT NULL UNIQUE,
    nickname TEXT,
    content TEXT,
    page_title TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chapters_manga ON chapters(manga_id);
CREATE INDEX IF NOT EXISTS idx_pages_chapter ON pages(chapter_id);
CREATE INDEX IF NOT EXISTS idx_manga_tags_manga ON manga_tags(manga_id);
CREATE INDEX IF NOT EXISTS idx_manga_tags_tag ON manga_tags(tag_id);

-- índices de expressão: get_or_create_tag/get_or_create_author buscam por
-- lower(name), que não usa o índice UNIQUE comum de `name` (esse é sobre a
-- coluna crua, não sobre o resultado de lower()).
CREATE INDEX IF NOT EXISTS idx_tags_name_lower ON tags(lower(name));
CREATE INDEX IF NOT EXISTS idx_authors_name_lower ON authors(lower(name));
