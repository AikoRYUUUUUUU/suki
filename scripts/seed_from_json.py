"""
Migra o conteúdo de data/db.json para o banco SQLite (mangadb.db).
Roda uma vez, manualmente: `python scripts/seed_from_json.py`.
Idempotente em relação ao schema (init_db cria as tabelas se faltarem),
mas insere duplicado se rodado duas vezes sobre o mesmo banco — rode só uma vez.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mangadb  # noqa: E402

JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "db.json")


def get_or_create(conn, table, name):
    if not name:
        return None
    row = conn.execute(f"SELECT id FROM {table} WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
    return cur.lastrowid


def main():
    mangadb.init_db()
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = mangadb.get_connection()
    try:
        for m in data["mangas"]:
            if conn.execute("SELECT 1 FROM mangas WHERE id = ?", (m["id"],)).fetchone():
                print(f"pulando '{m['id']}' (já existe)")
                continue

            author_id = get_or_create(conn, "authors", m.get("author"))
            group_id = get_or_create(conn, "groups", m.get("group")) if m.get("group") else None

            conn.execute("""
                INSERT INTO mangas (id, title, title_original, author_id, artist, group_id,
                                     status, year, rating, cover, synopsis)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                m["id"], m["title"], m.get("titleOriginal"), author_id, m.get("artist"), group_id,
                m["status"], m.get("year"), m.get("rating"), m.get("cover"), m["synopsis"],
            ))

            for genre in m.get("genres", []):
                tag_id = get_or_create(conn, "tags", genre)
                conn.execute(
                    "INSERT OR IGNORE INTO manga_tags (manga_id, tag_id) VALUES (?, ?)",
                    (m["id"], tag_id),
                )

            for ch in m.get("chapters", []):
                conn.execute("""
                    INSERT INTO chapters (id, manga_id, number, title, release_date)
                    VALUES (?, ?, ?, ?, ?)
                """, (ch["id"], m["id"], ch["number"], ch["title"], ch.get("releaseDate")))

                for i, page in enumerate(ch.get("pages", [])):
                    conn.execute("""
                        INSERT INTO pages (chapter_id, position, image_path)
                        VALUES (?, ?, ?)
                    """, (ch["id"], i, page))

            print(f"inserido '{m['id']}'")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
