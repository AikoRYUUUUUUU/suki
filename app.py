import os
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash

import mangadb

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_DEBUG") != "1"

ADMIN_USERNAME = os.environ["ADMIN_USERNAME"]
ADMIN_PASSWORD_HASH = os.environ["ADMIN_PASSWORD_HASH"]

csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[])

with app.app_context():
    mangadb.init_db()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# ---------- páginas públicas ----------

@app.route("/")
@app.route("/index.html")
def index():
    return render_template("index.html")


@app.route("/manga.html")
def manga_page():
    return render_template("manga.html")


@app.route("/reader.html")
def reader_page():
    return render_template("reader.html")


@app.route("/api/mangas")
def api_mangas():
    return jsonify({"mangas": mangadb.get_all_mangas_full()})


# ---------- autenticação do admin ----------

@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session.clear()
            session["is_admin"] = True
            next_url = request.args.get("next")
            if not next_url or not next_url.startswith("/"):
                next_url = url_for("admin")
            return redirect(next_url)
        error = "Usuário ou senha inválidos."
    return render_template("login.html", error=error)


@app.route("/admin/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- admin (protegido) ----------

@app.route("/admin", methods=["GET"])
@login_required
def admin():
    tags = mangadb.get_tags()
    authors = mangadb.get_authors()
    groups = mangadb.get_groups()
    return render_template("admin.html", tags=tags, authors=authors, groups=groups, error=None)


@app.route("/add_manga", methods=["POST"])
@login_required
def add_manga():
    try:
        mangadb.add_manga(
            title=request.form.get("title"),
            synopsis=request.form.get("synopsis"),
            status=request.form.get("status"),
            tag_ids=request.form.getlist("tag_ids"),
            author_id=request.form.get("author_id"),
            group_id=request.form.get("group_id"),
            title_original=request.form.get("title_original"),
            artist=request.form.get("artist"),
            year=request.form.get("year"),
            rating=request.form.get("rating"),
            cover=request.form.get("cover"),
        )
    except mangadb.ValidationError as e:
        tags = mangadb.get_tags()
        authors = mangadb.get_authors()
        groups = mangadb.get_groups()
        return render_template("admin.html", tags=tags, authors=authors, groups=groups, error=str(e)), 400
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
