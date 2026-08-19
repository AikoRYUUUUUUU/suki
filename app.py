import glob
import os
import secrets
import shutil
import time
from functools import wraps

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
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
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60MB por request (upload de páginas)

ADMIN_USERNAME = os.environ["ADMIN_USERNAME"]
ADMIN_PASSWORD_HASH = os.environ["ADMIN_PASSWORD_HASH"]

csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[])

with app.app_context():
    mangadb.init_db()


def sniff_image_extension(file_storage):
    """Identifica o tipo real da imagem pelos bytes (assinatura mágica), nunca pelo
    nome do arquivo ou pelo Content-Type declarado pelo cliente - ambos são
    informados pelo navegador/cliente e podem ser falsificados trivialmente."""
    head = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def covers_dir():
    return os.path.join(app.root_path, "static", "assets", "covers")


def pending_covers_dir():
    return os.path.join(covers_dir(), "_pending")


def cleanup_pending_covers(max_age_seconds=86400):
    """Remove capas temporárias abandonadas (form de preview nunca confirmado)."""
    folder = pending_covers_dir()
    if not os.path.isdir(folder):
        return
    cutoff = time.time() - max_age_seconds
    for f in glob.glob(os.path.join(folder, "*")):
        try:
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
        except OSError:
            pass


def save_pending_cover(cover_file, ext):
    """Salva a capa enviada no preview num arquivo temporário com token aleatório,
    devolve o token. Descarta qualquer capa pendente anterior desta mesma sessão."""
    folder = pending_covers_dir()
    os.makedirs(folder, exist_ok=True)

    old_token = session.get("pending_cover_token")
    if old_token:
        for f in glob.glob(os.path.join(folder, old_token + ".*")):
            os.remove(f)

    token = secrets.token_hex(16)
    cover_file.save(os.path.join(folder, f"{token}.{ext}"))
    session["pending_cover_token"] = token
    return token


def promote_pending_cover(token, manga_id):
    """Move a capa temporária (identificada só pelo token, nunca por nome de arquivo do
    cliente) pra seu lugar definitivo assets/covers/<manga_id>.<ext>, substituindo
    qualquer capa anterior desse mangá (mesmo se a extensão mudou)."""
    matches = glob.glob(os.path.join(pending_covers_dir(), token + ".*"))
    if not matches:
        return None
    src = matches[0]
    ext = src.rsplit(".", 1)[-1]

    folder = covers_dir()
    os.makedirs(folder, exist_ok=True)
    for old in glob.glob(os.path.join(folder, manga_id + ".*")):
        os.remove(old)

    dest = os.path.join(folder, f"{manga_id}.{ext}")
    shutil.move(src, dest)
    return f"assets/covers/{manga_id}.{ext}"


def save_manga_cover(manga_id, cover_file, ext):
    """Salva/substitui a capa definitiva de um mangá já existente (tela de editar capa)."""
    folder = covers_dir()
    os.makedirs(folder, exist_ok=True)
    for old in glob.glob(os.path.join(folder, manga_id + ".*")):
        os.remove(old)
    cover_file.save(os.path.join(folder, f"{manga_id}.{ext}"))
    return f"assets/covers/{manga_id}.{ext}"


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
    return render_template("admin.html", mangas=mangadb.get_dashboard_mangas())


@app.route("/admin/mangas/new", methods=["GET"])
@login_required
def new_manga_form():
    return render_template(
        "admin_new_manga.html",
        tags=mangadb.get_tags(), authors=mangadb.get_authors(), groups=mangadb.get_groups(),
        error=None,
    )


def render_new_manga_error(message):
    return render_template(
        "admin_new_manga.html",
        tags=mangadb.get_tags(), authors=mangadb.get_authors(), groups=mangadb.get_groups(),
        error=message,
    ), 400


@app.route("/admin/mangas/preview", methods=["POST"])
@login_required
def preview_manga():
    cleanup_pending_covers()

    try:
        fields = mangadb.validate_manga_fields(
            title=request.form.get("title"),
            synopsis=request.form.get("synopsis"),
            status=request.form.get("status"),
            tag_ids=request.form.getlist("tag_ids"),
            author_id=request.form.get("author_id"),
            group_id=request.form.get("group_id"),
            year=request.form.get("year"),
            rating=request.form.get("rating"),
        )
    except mangadb.ValidationError as e:
        return render_new_manga_error(str(e))

    cover_token = ""
    cover_preview_url = None
    cover_file = request.files.get("cover")
    if cover_file and cover_file.filename:
        ext = sniff_image_extension(cover_file)
        if ext is None:
            return render_new_manga_error("A imagem da capa não é válida (png, jpg, webp).")
        cover_token = save_pending_cover(cover_file, ext)
        cover_preview_url = f"/static/assets/covers/_pending/{cover_token}.{ext}"

    tags_by_id = {t["id"]: t["name"] for t in mangadb.get_tags()}
    tag_names = [tags_by_id[t] for t in fields["tag_ids"] if t in tags_by_id]
    author_name = next(
        (a["name"] for a in mangadb.get_authors() if a["id"] == fields["author_id"]), None
    )
    group_name = next(
        (g["name"] for g in mangadb.get_groups() if g["id"] == fields["group_id"]), None
    )

    return render_template(
        "admin_confirm_manga.html",
        fields=fields,
        title_original=(request.form.get("title_original") or "").strip(),
        artist=(request.form.get("artist") or "").strip(),
        tag_names=tag_names, author_name=author_name, group_name=group_name,
        cover_preview_url=cover_preview_url, cover_token=cover_token,
    )


@app.route("/admin/mangas", methods=["POST"])
@login_required
def create_manga():
    try:
        manga_id = mangadb.add_manga(
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
        )
    except mangadb.ValidationError as e:
        return render_new_manga_error(str(e))

    cover_token = request.form.get("cover_token")
    if cover_token:
        cover_path = promote_pending_cover(cover_token, manga_id)
        if cover_path:
            mangadb.update_manga_cover(manga_id, cover_path)
        session.pop("pending_cover_token", None)

    return redirect(url_for("admin"))


@app.route("/admin/mangas/<manga_id>/cover", methods=["GET"])
@login_required
def edit_cover_form(manga_id):
    title = mangadb.get_manga_title(manga_id)
    if title is None:
        abort(404)
    return render_template(
        "admin_edit_cover.html",
        manga_id=manga_id, manga_title=title,
        current_cover=mangadb.static_url(mangadb.get_manga_cover(manga_id)),
        error=None,
    )


@app.route("/admin/mangas/<manga_id>/cover", methods=["POST"])
@login_required
def update_cover(manga_id):
    title = mangadb.get_manga_title(manga_id)
    if title is None:
        abort(404)

    def render_error(message):
        return render_template(
            "admin_edit_cover.html",
            manga_id=manga_id, manga_title=title,
            current_cover=mangadb.static_url(mangadb.get_manga_cover(manga_id)),
            error=message,
        ), 400

    cover_file = request.files.get("cover")
    if not cover_file or not cover_file.filename:
        return render_error("Selecione uma imagem.")

    ext = sniff_image_extension(cover_file)
    if ext is None:
        return render_error("Arquivo não é uma imagem válida (png, jpg, webp).")

    cover_path = save_manga_cover(manga_id, cover_file, ext)
    mangadb.update_manga_cover(manga_id, cover_path)
    return redirect(url_for("admin"))


@app.route("/admin/mangas/<manga_id>/chapters/new", methods=["GET"])
@login_required
def new_chapter_form(manga_id):
    title = mangadb.get_manga_title(manga_id)
    if title is None:
        abort(404)
    return render_template(
        "admin_new_chapter.html",
        manga_id=manga_id, manga_title=title,
        next_number=mangadb.format_number(mangadb.next_chapter_number(manga_id)),
        error=None,
    )


def save_chapter_pages(manga_id, chapter_id, files, extensions):
    """Salva as imagens de página em disco com nomes gerados pelo servidor
    (nunca o nome original do upload) e devolve os caminhos relativos pra gravar no banco.
    `extensions` já veio validada pelos bytes reais de cada arquivo (sniff_image_extension)."""
    folder = os.path.join(app.root_path, "static", "assets", "pages", manga_id, chapter_id)
    os.makedirs(folder, exist_ok=True)
    try:
        paths = []
        for position, (file, ext) in enumerate(zip(files, extensions)):
            filename = f"{position:03d}.{ext}"
            file.save(os.path.join(folder, filename))
            paths.append(f"assets/pages/{manga_id}/{chapter_id}/{filename}")
        return paths
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


@app.route("/admin/mangas/<manga_id>/chapters", methods=["POST"])
@login_required
def create_chapter(manga_id):
    manga_title = mangadb.get_manga_title(manga_id)
    if manga_title is None:
        abort(404)

    def render_error(message, status=400):
        return render_template(
            "admin_new_chapter.html",
            manga_id=manga_id, manga_title=manga_title,
            next_number=mangadb.format_number(mangadb.next_chapter_number(manga_id)),
            error=message,
        ), status

    try:
        number_val, title = mangadb.validate_chapter_fields(
            request.form.get("number"), request.form.get("title")
        )
    except mangadb.ValidationError as e:
        return render_error(str(e))

    files = [f for f in request.files.getlist("pages") if f and f.filename]
    if not files:
        return render_error("Selecione ao menos uma imagem de página.")

    extensions = []
    for file in files:
        ext = sniff_image_extension(file)
        if ext is None:
            return render_error(f"Arquivo '{file.filename}' não é uma imagem válida (png, jpg, webp).")
        extensions.append(ext)

    chapter_id = mangadb.build_chapter_id(manga_id, number_val)
    page_paths = save_chapter_pages(manga_id, chapter_id, files, extensions)

    try:
        mangadb.add_chapter(
            manga_id=manga_id, chapter_id=chapter_id, number_val=number_val, title=title,
            release_date=request.form.get("release_date"), page_paths=page_paths,
        )
    except mangadb.ValidationError as e:
        shutil.rmtree(
            os.path.join(app.root_path, "static", "assets", "pages", manga_id, chapter_id),
            ignore_errors=True,
        )
        return render_error(str(e))

    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
