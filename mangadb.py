import sqlite3

def get_connection():
    conn = sqlite3.connect('mangadb.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_tags():
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM tags")
    tags = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tags

def get_authors():
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM authors")
    authors = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return authors

def get_groups():
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM groups")
    groups = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return groups

def add_manga(title, description, tag_ids, author_id, group_id):
    conn = get_connection()
    cursor = conn.cursor()

    # Inserir o mangá
    cursor.execute("INSERT INTO mangas (title, description, author_id, group_id) VALUES (?, ?, ?, ?)", 
                   (title, description, author_id, group_id))
    manga_id = cursor.lastrowid

    # Inserir as tags associadas
    for tag_id in tag_ids:
        cursor.execute("INSERT INTO manga_tags (manga_id, tag_id) VALUES (?, ?)", (manga_id, tag_id))

    conn.commit()
    conn.close()
