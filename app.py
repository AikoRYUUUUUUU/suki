import hashlib
import hmac
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import urllib.request
from datetime import date
from functools import wraps
from pathlib import Path

import nacl.exceptions
import nacl.signing
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash

import mangadb
import r2

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_DEBUG") != "1"
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # imagens não passam mais pelo Flask (vão direto pro R2)

ADMIN_USERNAME = os.environ["ADMIN_USERNAME"]
ADMIN_PASSWORD_HASH = os.environ["ADMIN_PASSWORD_HASH"]
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
WSGI_FILE_PATH = os.environ.get("WSGI_FILE_PATH")
GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY")
DISCORD_ROLES_CHANNEL_ID = os.environ.get("DISCORD_ROLES_CHANNEL_ID")

SITE_DESCRIPTION = "Leia mangás e webtoons traduzidos em português, de graça e sem enrolação. Catálogo atualizado toda semana."

csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[])
app.jinja_env.globals["format_number"] = mangadb.format_number

with app.app_context():
    mangadb.init_db()


def truncate_words(text, limit):
    """Corta no último espaço antes do limite, pra description de meta tag não
    quebrar palavra no meio (motores de busca e redes sociais truncam sem isso)."""
    if not text or len(text) <= limit:
        return text or ""
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "…"


def absolute_url(path):
    """og:url/og:image precisam de URL absoluta - request.url_root já reflete
    o esquema (http/https) e host reais da requisição, sem precisar fixar domínio."""
    return request.url_root.rstrip("/") + path


def default_og_image():
    return absolute_url(url_for("static", filename="assets/og-banner.png"))


def og_image_url(cover):
    """Capas locais vêm de static_url() como caminho relativo (/static/...); as do
    R2 já são https:// absolutas. og:image exige URL absoluta nos dois casos."""
    if not cover:
        return default_og_image()
    if cover.startswith(("http://", "https://")):
        return cover
    return absolute_url(cover)


def notify_discord(title, url, description, cover, role_id=None, synopsis=None):
    """Dispara o webhook de anúncio no Discord. Best-effort: sem
    DISCORD_WEBHOOK_URL configurada, ou se o Discord estiver fora do ar, não
    pode derrubar o fluxo de publicação do admin - só loga e segue."""
    if not DISCORD_WEBHOOK_URL:
        return
    embed = {
        "title": title,
        "url": url,
        "description": description,
        "color": 0xB7472A,
        "image": {"url": og_image_url(cover)},
        "footer": {"text": "Equipe Suki Mangás"},
    }
    if synopsis:
        embed["fields"] = [{"name": "Sinopse", "value": truncate_words(synopsis, 300)}]
    payload = {"embeds": [embed]}
    if role_id:
        # Menção só notifica quem tem o cargo se estiver em "content" - dentro do
        # embed (título/descrição) o Discord não interpreta como menção de verdade.
        payload["content"] = f"<@&{role_id}>"
        payload["allowed_mentions"] = {"parse": [], "roles": [role_id]}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            # Mesmo bug do Cloudflare barrando User-Agent genérico do urllib
            # que já apareceu em discord_api() e no endpoint de interações.
            "User-Agent": "SukiBot (https://sukimangas.pythonanywhere.com, 1.0)",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[discord webhook] falhou: {e}")


def discord_api(method, path, body=None):
    """Chamada crua na API REST do Discord, autenticada como bot. Sem
    User-Agent descritivo o Cloudflare na frente do discord.com barra o
    request (parece automação) com erro 403."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"https://discord.com/api/v10{path}", data=data, method=method,
        headers={
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "SukiBot (https://sukimangas.pythonanywhere.com, 1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def create_discord_role(title):
    """Cria direto na API do Discord o cargo de 'seguir esse mangá' e devolve o
    ID. Best-effort - sem token configurado ou com o Discord fora do ar, o
    mangá é criado normalmente sem cargo."""
    if not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID:
        return None
    try:
        role = discord_api(
            "POST", f"/guilds/{DISCORD_GUILD_ID}/roles",
            {"name": title[:100], "mentionable": True, "hoist": False},
        )
        return role.get("id")
    except Exception as e:
        print(f"[discord] criação de cargo falhou: {e}")
        return None


def rename_discord_role(role_id, title):
    """Best-effort - mantém o nome do cargo em dia com o título do mangá."""
    if not role_id or not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID:
        return
    try:
        discord_api("PATCH", f"/guilds/{DISCORD_GUILD_ID}/roles/{role_id}", {"name": title[:100]})
    except Exception as e:
        print(f"[discord] renomear cargo falhou: {e}")


def delete_discord_role(role_id):
    """Best-effort - evita cargo órfão no Discord quando o mangá é apagado."""
    if not role_id or not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID:
        return
    try:
        discord_api("DELETE", f"/guilds/{DISCORD_GUILD_ID}/roles/{role_id}")
    except Exception as e:
        print(f"[discord] exclusão de cargo falhou: {e}")


CSP = (
    "default-src 'self'; "
    "img-src 'self' https://*.r2.dev; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self' https://graphql.anilist.co https://*.r2.cloudflarestorage.com https://translate.googleapis.com; "
    "frame-ancestors 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)  # se a URL pública do R2 (R2_PUBLIC_BASE_URL) virar um domínio próprio em vez de
   # *.r2.dev, o img-src acima precisa ser atualizado junto


@app.after_request
def set_security_headers(response):
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def is_r2_url(path):
    return bool(path) and path.startswith(("http://", "https://"))


def get_client_ip():
    """PythonAnywhere fica atrás do proxy deles, então `request.remote_addr` sozinho
    daria o IP do proxy pra todo mundo (colidindo os votos de leitores diferentes).
    X-Forwarded-For, quando presente, tem o IP real do visitante primeiro na lista."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def voter_hash():
    """Impressão digital do leitor pra travar voto duplicado - hash do IP com o
    SECRET_KEY como tempero, então não dá pra reverter pro IP original a partir
    do que fica gravado em `votes`."""
    raw = get_client_ip() + app.config["SECRET_KEY"]
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    return render_template(
        "index.html",
        statuses=mangadb.MANGA_STATUSES,
        meta_description=SITE_DESCRIPTION,
        canonical_url=absolute_url(url_for("index")),
        og_image=default_og_image(),
        google_site_verification=GOOGLE_SITE_VERIFICATION,
    )


@app.route("/busca.html")
def search_page():
    q = request.args.get("q", "").strip()
    meta_description = f'Resultados da busca por "{q}" — {SITE_DESCRIPTION}' if q else SITE_DESCRIPTION
    return render_template(
        "busca.html",
        statuses=mangadb.MANGA_STATUSES,
        tag_groups=mangadb.TAG_GROUPS,
        sensitive_tags=mangadb.SENSITIVE_TAGS,
        q=q,
        status=request.args.get("status", "").strip(),
        selected_tags=request.args.getlist("tags"),
        meta_description=meta_description,
        canonical_url=absolute_url(url_for("search_page")),
        og_image=default_og_image(),
    )


@app.route("/manga.html")
def manga_page():
    manga = mangadb.get_manga_public(request.args.get("id", ""))
    structured_data = None
    if manga:
        page_title = f"{manga['title']} — Suki"
        meta_description = truncate_words(manga["synopsis"], 160) or SITE_DESCRIPTION
        og_image = og_image_url(manga["cover"])
        structured_data = {
            "@context": "https://schema.org",
            "@type": "Book",
            "name": manga["title"],
            "bookFormat": "https://schema.org/GraphicNovel",
            "url": absolute_url(request.full_path.rstrip("?")),
            "image": og_image,
            "description": manga["synopsis"],
            "genre": manga["genres"],
        }
        if manga["titleOriginal"]:
            structured_data["alternateName"] = manga["titleOriginal"]
        if manga["author"]:
            structured_data["author"] = {"@type": "Person", "name": manga["author"]}
        if manga["ratingCount"]:
            structured_data["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": manga["rating"],
                "ratingCount": manga["ratingCount"],
                "bestRating": 5,
                "worstRating": 1,
            }
    else:
        page_title = "Mangá não encontrado — Suki"
        meta_description = SITE_DESCRIPTION
        og_image = default_og_image()

    return render_template(
        "manga.html",
        manga=manga,
        page_title=page_title,
        meta_description=meta_description,
        canonical_url=absolute_url(request.full_path.rstrip("?")),
        og_image=og_image,
        structured_data=structured_data,
    )


@app.route("/reader.html")
def reader_page():
    chapter = mangadb.get_chapter_public(
        request.args.get("id", ""), request.args.get("ch", "")
    )
    if chapter:
        chapter_label = mangadb.format_number(chapter["number"])
        page_title = f"Cap. {chapter_label} — {chapter['mangaTitle']} — Suki"
        meta_description = f"Leia o capítulo {chapter_label} de {chapter['mangaTitle']} grátis em Suki."
        og_image = og_image_url(chapter["cover"])
    else:
        page_title = "Leitor — Suki"
        meta_description = SITE_DESCRIPTION
        og_image = default_og_image()

    return render_template(
        "reader.html",
        chapter=chapter,
        page_title=page_title,
        meta_description=meta_description,
        canonical_url=absolute_url(request.full_path.rstrip("?")),
        og_image=og_image,
    )


@app.route("/robots.txt")
def robots_txt():
    body = (
        "User-agent: *\n"
        "Disallow: /admin\n"
        "Disallow: /deploy\n"
        "Disallow: /webhooks/\n\n"
        f"Sitemap: {absolute_url(url_for('sitemap_xml'))}\n"
    )
    return app.response_class(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    urls = [
        absolute_url(url_for("index")),
        absolute_url(url_for("search_page")),
    ]
    urls += [
        absolute_url(url_for("manga_page")) + f"?id={manga_id}"
        for manga_id in mangadb.get_all_manga_ids()
    ]
    xml_urls = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    body = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml_urls}</urlset>'
    return app.response_class(body, mimetype="application/xml")


@app.route("/google88b36d17adab0dc2.html")
def google_site_verification_file():
    return app.response_class("google-site-verification: google88b36d17adab0dc2.html\n", mimetype="text/html")


@app.route("/api/mangas")
def api_mangas():
    return jsonify({"mangas": mangadb.get_all_mangas_full()})


@app.route("/api/mangas/<manga_id>/rate", methods=["POST"])
@csrf.exempt
@limiter.limit("20 per minute")
def rate_manga(manga_id):
    if not mangadb.manga_exists(manga_id):
        abort(404)

    data = request.get_json(silent=True) or {}
    value = data.get("value")
    if not isinstance(value, int) or value < 1 or value > 5:
        abort(400)

    try:
        rating, rating_count = mangadb.add_vote(manga_id, voter_hash(), value)
    except sqlite3.IntegrityError:
        return jsonify({"error": "already_voted"}), 409

    return jsonify({"rating": rating, "ratingCount": rating_count})


COMMENT_NAME_MAX = 50
COMMENT_BODY_MAX = 2000


@app.route("/api/mangas/<manga_id>/comments", methods=["GET"])
def list_comments(manga_id):
    if not mangadb.manga_exists(manga_id):
        abort(404)
    return jsonify({"comments": mangadb.get_comments(manga_id)})


@app.route("/api/mangas/<manga_id>/comments", methods=["POST"])
@csrf.exempt
@limiter.limit("6 per minute")
def create_comment(manga_id):
    if not mangadb.manga_exists(manga_id):
        abort(404)

    data = request.get_json(silent=True) or {}

    # Honeypot: campo escondido via CSS que só bot preenche - finge sucesso
    # sem gravar nada, pra não denunciar pro spammer que foi filtrado.
    if (data.get("website") or "").strip():
        return jsonify({"ok": True}), 201

    author_name = (data.get("author_name") or "").strip()
    body = (data.get("body") or "").strip()
    parent_id = data.get("parent_id")

    if not author_name or len(author_name) > COMMENT_NAME_MAX:
        abort(400)
    if not body or len(body) > COMMENT_BODY_MAX:
        abort(400)
    if parent_id is not None:
        if not isinstance(parent_id, int) or not mangadb.comment_exists(parent_id):
            abort(400)

    comment_id = mangadb.add_comment(manga_id, parent_id, author_name, body)
    return jsonify({"id": comment_id}), 201


@app.route("/api/comments/<int:comment_id>/vote", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per minute")
def vote_on_comment(comment_id):
    if not mangadb.comment_exists(comment_id):
        abort(404)

    data = request.get_json(silent=True) or {}
    value = data.get("value")
    if value not in (1, -1):
        abort(400)

    try:
        score = mangadb.vote_comment(comment_id, voter_hash(), value)
    except sqlite3.IntegrityError:
        return jsonify({"error": "already_voted"}), 409

    return jsonify({"score": score})


# ---------- auto-deploy (webhook do GitHub) ----------

def verify_github_signature(payload_body, signature_header):
    if not GITHUB_WEBHOOK_SECRET or not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@app.route("/deploy", methods=["POST"])
@csrf.exempt
@limiter.limit("10 per minute")
def deploy():
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(request.get_data(), signature):
        abort(403)

    payload = request.get_json(silent=True) or {}
    if payload.get("ref") not in (None, "refs/heads/master"):
        return "ignored", 200

    try:
        result = subprocess.run(
            ["git", "pull"], cwd=app.root_path,
            capture_output=True, text=True, timeout=60, check=False,
        )
        print(f"[deploy] git pull rc={result.returncode} out={result.stdout!r} err={result.stderr!r}")

        if WSGI_FILE_PATH:
            Path(WSGI_FILE_PATH).touch()
        else:
            print("[deploy] WSGI_FILE_PATH não configurado - reload não disparado automaticamente")
    except Exception as e:
        print(f"[deploy] falhou: {e}")
        return "error", 500

    return "ok", 200

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
    candidates = mangadb.get_migration_candidates()
    migration_pending_count = len(candidates["covers"]) + len(candidates["pages"])
    discord_roles_pending = (
        mangadb.get_mangas_without_discord_role()
        if DISCORD_BOT_TOKEN and DISCORD_GUILD_ID else []
    )
    return render_template(
        "admin.html",
        mangas=mangadb.get_dashboard_mangas(),
        statuses=mangadb.MANGA_STATUSES,
        migration_pending_count=migration_pending_count,
        discord_roles_pending_count=len(discord_roles_pending),
        discord_roles_announce_ready=bool(DISCORD_BOT_TOKEN and DISCORD_ROLES_CHANNEL_ID),
    )


@app.route("/admin/discord-roles/backfill", methods=["POST"])
@login_required
def backfill_discord_roles():
    """Cria o cargo no Discord pros mangás que ficaram sem (cadastrados antes
    do bot existir, ou que falharam na hora - Discord fora do ar, etc)."""
    for manga in mangadb.get_mangas_without_discord_role():
        role_id = create_discord_role(manga["title"])
        if role_id:
            mangadb.set_manga_discord_role(manga["id"], role_id)
    return redirect(url_for("admin"))


@app.route("/admin/discord-roles/announce", methods=["POST"])
@login_required
def announce_discord_roles():
    """Manda no canal configurado uma mensagem por lote de até 25 mangás (5
    linhas de 5 botões), cada botão com o cargo daquele mangá. Clicar liga/
    desliga o cargo (ver discord_interactions)."""
    mangas = mangadb.get_mangas_with_discord_role()
    if not mangas or not DISCORD_BOT_TOKEN or not DISCORD_ROLES_CHANNEL_ID:
        return redirect(url_for("admin"))

    def button_label(m):
        label = ("🔞 " if m["is_sensitive"] else "") + m["title"]
        return label[:80]

    batches = [mangas[i:i + 25] for i in range(0, len(mangas), 25)]
    for i, batch in enumerate(batches):
        rows = [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 2,
                        "label": button_label(m),
                        "custom_id": f"role:{m['discord_role_id']}",
                    }
                    for m in batch[j:j + 5]
                ],
            }
            for j in range(0, len(batch), 5)
        ]
        payload = {"components": rows}
        if i == 0:
            payload["content"] = (
                "Cada mangá listado abaixo tem um cargo próprio. Clique no botão "
                "com o nome do mangá pra receber esse cargo e ser marcado aqui "
                "sempre que sair capítulo novo.\n"
                "Pra parar de receber, clique de novo no mesmo botão — o cargo "
                "sai na hora, sem precisar pedir pra ninguém.\n\n"
                "— Equipe Suki Mangás"
            )
            catalog_lines = "\n".join(
                f"🔞 {m['title']}" if m["is_sensitive"] else f"• {m['title']}"
                for m in mangas  # já vem em ordem alfabética de get_mangas_with_discord_role
            )
            sensitive_note = "\n\n🔞 = conteúdo sensível (+18)" if any(m["is_sensitive"] for m in mangas) else ""
            payload["embeds"] = [{
                "title": "📚 Notificações por mangá",
                "description": f"{catalog_lines}{sensitive_note}",
                "color": 0xB7472A,
                "image": {"url": default_og_image()},
                "footer": {"text": "Suki"},
            }]
        try:
            discord_api("POST", f"/channels/{DISCORD_ROLES_CHANNEL_ID}/messages", payload)
        except Exception as e:
            print(f"[discord] envio da mensagem de cargos falhou: {e}")
            break

    return redirect(url_for("admin"))


@app.route("/discord/interactions", methods=["POST"])
@csrf.exempt
def discord_interactions():
    """Endpoint público que o Discord chama quando alguém clica num botão de
    cargo. Autenticidade vem da assinatura Ed25519 (não tem CSRF/login - quem
    prova que é o Discord é a assinatura), não de sessão/CSRF."""
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    body = request.get_data()
    try:
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        verify_key.verify(timestamp.encode("utf-8") + body, bytes.fromhex(signature))
    except (nacl.exceptions.BadSignatureError, ValueError, TypeError):
        abort(401)

    data = request.get_json(silent=True) or {}

    if data.get("type") == 1:  # PING de verificação do endpoint
        return jsonify({"type": 1})

    if data.get("type") == 3:  # clique num botão
        custom_id = data.get("data", {}).get("custom_id", "")
        if custom_id.startswith("role:"):
            role_id = custom_id[len("role:"):]
            member = data.get("member") or {}
            user_id = member.get("user", {}).get("id")
            has_role = role_id in (member.get("roles") or [])
            try:
                if has_role:
                    discord_api("DELETE", f"/guilds/{DISCORD_GUILD_ID}/members/{user_id}/roles/{role_id}")
                    content = "❌ Você não vai mais receber avisos desse mangá."
                else:
                    discord_api("PUT", f"/guilds/{DISCORD_GUILD_ID}/members/{user_id}/roles/{role_id}")
                    content = "✅ Você vai receber avisos de capítulo novo desse mangá!"
            except Exception as e:
                print(f"[discord] toggle de cargo falhou: {e}")
                content = "Deu ruim aqui, tenta de novo daqui a pouco."
            return jsonify({"type": 4, "data": {"content": content, "flags": 64}})

    if data.get("type") == 2:  # slash command
        return handle_slash_command(data.get("data") or {})

    return jsonify({"type": 4, "data": {"content": "Interação não reconhecida.", "flags": 64}})


def manga_embed(manga, title=None):
    return {
        "title": title or manga["title"],
        "url": absolute_url(url_for("manga_page")) + f"?id={manga['id']}",
        "description": truncate_words(manga["synopsis"] or "", 200),
        "color": 0xB7472A,
        "thumbnail": {"url": og_image_url(manga["cover"])},
        "footer": {"text": "Equipe Suki Mangás"},
    }


def handle_slash_command(command):
    """Respostas sempre com flags:64 (ephemeral) - só quem digitou o comando
    vê a resposta, o resto do canal não é poluído."""
    name = command.get("name")

    if name == "procurar":
        options = {o["name"]: o["value"] for o in command.get("options", [])}
        query = (options.get("nome") or "").strip()
        results = mangadb.search_mangas_by_title(query, limit=5) if query else []
        if not results:
            return jsonify({"type": 4, "data": {
                "content": f'Não achei nenhum mangá com "{query}" no catálogo.', "flags": 64,
            }})
        return jsonify({"type": 4, "data": {
            "embeds": [manga_embed(m) for m in results], "flags": 64,
        }})

    if name == "aleatorio":
        manga = mangadb.get_random_manga()
        if not manga:
            return jsonify({"type": 4, "data": {"content": "O catálogo tá vazio no momento.", "flags": 64}})
        return jsonify({"type": 4, "data": {
            "embeds": [manga_embed(manga, title=f"🎲 {manga['title']}")], "flags": 64,
        }})

    return jsonify({"type": 4, "data": {"content": "Comando não reconhecido.", "flags": 64}})


@app.route("/admin/uploads/presign", methods=["POST"])
@login_required
def presign_upload():
    """Confere os bytes reais enviados (magic bytes, não nome/Content-Type do
    cliente) e devolve uma URL PUT pré-assinada pro R2 - o navegador do admin
    envia o arquivo direto pro bucket, sem passar pelo Flask/PythonAnywhere."""
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    if kind not in ("cover", "page"):
        abort(400)

    manga_id = data.get("manga_id")
    if kind == "page":
        if not manga_id or not mangadb.manga_exists(manga_id):
            abort(400)

    head = data.get("head")
    if not isinstance(head, list) or not head:
        abort(400)
    try:
        head_bytes = bytes(head)
    except (TypeError, ValueError):
        abort(400)

    ext = r2.sniff_bytes(head_bytes)
    if ext is None:
        return jsonify({"error": "Arquivo não é uma imagem válida (png, jpg, webp)."}), 400

    if kind == "cover":
        key = f"covers/{secrets.token_hex(16)}.{ext}"
    else:
        key = f"pages/{manga_id}/{secrets.token_hex(8)}.{ext}"

    try:
        upload_url = r2.presign_put(key)
    except r2.R2NotConfigured as e:
        return jsonify({"error": str(e)}), 503

    return jsonify({
        "upload_url": upload_url,
        "public_url": r2.public_url(key),
        "content_type": r2.CONTENT_TYPES[ext],
        "key": key,
    })


@app.route("/admin/r2/presign-delete", methods=["POST"])
@login_required
def presign_delete():
    """Devolve URLs DELETE pré-assinadas pras URLs informadas que forem
    hospedadas no nosso bucket R2 (ignora caminhos locais legados)."""
    data = request.get_json(silent=True) or {}
    urls = data.get("urls")
    if not isinstance(urls, list):
        abort(400)

    result = {}
    for url in urls:
        key = r2.key_from_public_url(url)
        if key is None:
            continue
        try:
            result[url] = r2.presign_delete(key)
        except r2.R2NotConfigured:
            continue
    return jsonify({"urls": result})


def _manga_r2_urls(manga_id):
    urls = []
    cover = mangadb.get_manga_cover(manga_id)
    if is_r2_url(cover):
        urls.append(cover)
    for p in mangadb.get_manga_pages_with_paths(manga_id):
        if is_r2_url(p["image_path"]):
            urls.append(p["image_path"])
    return urls


@app.route("/admin/mangas/<manga_id>/r2-delete-urls", methods=["POST"])
@login_required
def manga_r2_delete_urls(manga_id):
    if not mangadb.manga_exists(manga_id):
        abort(404)
    result = {}
    for url in _manga_r2_urls(manga_id):
        key = r2.key_from_public_url(url)
        try:
            result[url] = r2.presign_delete(key)
        except r2.R2NotConfigured:
            continue
    return jsonify({"urls": result})


@app.route("/admin/mangas/<manga_id>/chapters/<chapter_id>/r2-delete-urls", methods=["POST"])
@login_required
def chapter_r2_delete_urls(manga_id, chapter_id):
    chapter = mangadb.get_chapter_edit_data(manga_id, chapter_id)
    if chapter is None:
        abort(404)
    result = {}
    for p in chapter["pages"]:
        if not is_r2_url(p["image_path"]):
            continue
        key = r2.key_from_public_url(p["image_path"])
        try:
            result[p["image_path"]] = r2.presign_delete(key)
        except r2.R2NotConfigured:
            continue
    return jsonify({"urls": result})


@app.route("/admin/migration/pending", methods=["GET"])
@login_required
def migration_pending():
    """Capas/páginas ainda em disco local (upload de antes da migração pro R2).
    O navegador do admin busca cada arquivo via sua própria URL /static/ (mesma
    origem, não é 'saída' pro PythonAnywhere) e reenvia pro R2 usando o mesmo
    presign de sempre - ver static/js/admin_migration.js."""
    candidates = mangadb.get_migration_candidates()
    items = [
        {
            "kind": "cover", "manga_id": c["manga_id"], "label": c["title"],
            "local_url": mangadb.static_url(c["path"]),
        }
        for c in candidates["covers"]
    ] + [
        {
            "kind": "page", "page_id": p["page_id"], "manga_id": p["manga_id"], "label": f"página #{p['page_id']}",
            "local_url": mangadb.static_url(p["path"]),
        }
        for p in candidates["pages"]
    ]
    return jsonify({"items": items})


@app.route("/admin/migration/commit", methods=["POST"])
@login_required
def migration_commit():
    """Grava a URL R2 já enviada pelo navegador no lugar do caminho local
    correspondente, e só então apaga o arquivo local antigo (nessa ordem - nunca
    apaga antes de confirmar que a nova URL é válida e foi persistida)."""
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    url = data.get("url")
    if not is_r2_url(url) or r2.key_from_public_url(url) is None:
        abort(400)
    size = data.get("size")
    size_bytes = int(size) if isinstance(size, (int, float)) else None

    if kind == "cover":
        manga_id = data.get("manga_id")
        if not manga_id or not mangadb.manga_exists(manga_id):
            abort(404)
        old_path = mangadb.get_manga_cover(manga_id)
        if is_r2_url(old_path):
            return jsonify({"ok": True, "already_migrated": True})
        mangadb.update_manga_cover(manga_id, url)
        if old_path:
            old_full_path = os.path.join(app.root_path, "static", *old_path.split("/"))
            if os.path.exists(old_full_path):
                os.remove(old_full_path)
        return jsonify({"ok": True})

    if kind == "page":
        page_id = data.get("page_id")
        page = mangadb.get_page_by_id(page_id)
        if page is None or page["manga_id"] != data.get("manga_id"):
            abort(404)
        old_path = page["image_path"]
        if is_r2_url(old_path):
            return jsonify({"ok": True, "already_migrated": True})
        mangadb.update_page_image(page_id, url, size_bytes)
        if mangadb.count_pages_with_image_path(old_path, exclude_ids=[page_id]) == 0:
            old_full_path = os.path.join(app.root_path, "static", *old_path.split("/"))
            if os.path.exists(old_full_path):
                os.remove(old_full_path)
        return jsonify({"ok": True})

    abort(400)


@app.route("/admin/mangas/<manga_id>/comments", methods=["GET"])
@login_required
def manga_comments_admin(manga_id):
    manga_title = mangadb.get_manga_title(manga_id)
    if manga_title is None:
        abort(404)
    return render_template(
        "admin_manga_comments.html",
        manga_id=manga_id, manga_title=manga_title,
        comments=mangadb.get_comments(manga_id),
    )


@app.route("/admin/mangas/<manga_id>/comments/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment_route(manga_id, comment_id):
    mangadb.delete_comment(comment_id)
    return redirect(url_for("manga_comments_admin", manga_id=manga_id))


@app.route("/admin/mangas/<manga_id>/status", methods=["POST"])
@login_required
def update_status(manga_id):
    if not mangadb.manga_exists(manga_id):
        abort(404)
    status = request.form.get("status")
    if status not in mangadb.MANGA_STATUSES:
        abort(400)
    mangadb.update_manga_status(manga_id, status)
    return redirect(url_for("admin"))


@app.route("/admin/mangas/new", methods=["GET"])
@login_required
def new_manga_form():
    return render_template(
        "admin_new_manga.html", groups=mangadb.get_groups(),
        statuses=mangadb.MANGA_STATUSES, tag_groups=mangadb.TAG_GROUPS,
        sensitive_tags=mangadb.SENSITIVE_TAGS, error=None,
    )


def render_new_manga_error(message):
    return render_template(
        "admin_new_manga.html", groups=mangadb.get_groups(),
        statuses=mangadb.MANGA_STATUSES, tag_groups=mangadb.TAG_GROUPS,
        sensitive_tags=mangadb.SENSITIVE_TAGS, error=message,
    ), 400


@app.route("/admin/mangas/preview", methods=["POST"])
@login_required
def preview_manga():
    try:
        fields = mangadb.validate_manga_fields(
            title=request.form.get("title"),
            synopsis=request.form.get("synopsis"),
            status=request.form.get("status"),
            tags=",".join(request.form.getlist("tags")),
            author=request.form.get("author"),
            group_id=request.form.get("group_id"),
            year=request.form.get("year"),
            rating=request.form.get("rating"),
        )
    except mangadb.ValidationError as e:
        return render_new_manga_error(str(e))

    cover_url = (request.form.get("cover_url") or "").strip()

    group_name = next(
        (g["name"] for g in mangadb.get_groups() if g["id"] == fields["group_id"]), None
    )

    return render_template(
        "admin_confirm_manga.html",
        fields=fields,
        title_original=(request.form.get("title_original") or "").strip(),
        artist=(request.form.get("artist") or "").strip(),
        tag_names=fields["tag_names"], author_name=fields["author"] or None, group_name=group_name,
        cover_url=cover_url,
    )


@app.route("/admin/mangas", methods=["POST"])
@login_required
def create_manga():
    cover_url = (request.form.get("cover_url") or "").strip()
    try:
        manga_id = mangadb.add_manga(
            title=request.form.get("title"),
            synopsis=request.form.get("synopsis"),
            status=request.form.get("status"),
            tags=request.form.get("tags"),
            author=request.form.get("author"),
            group_id=request.form.get("group_id"),
            title_original=request.form.get("title_original"),
            artist=request.form.get("artist"),
            year=request.form.get("year"),
            rating=request.form.get("rating"),
            cover=cover_url or None,
        )
    except mangadb.ValidationError as e:
        return render_new_manga_error(str(e))

    role_id = create_discord_role(request.form.get("title"))
    if role_id:
        mangadb.set_manga_discord_role(manga_id, role_id)

    notify_discord(
        title=f"📚 Novo mangá: {request.form.get('title')}",
        url=absolute_url(url_for("manga_page")) + f"?id={manga_id}",
        description=truncate_words(request.form.get("synopsis") or "", 300),
        cover=mangadb.static_url(cover_url) if cover_url else None,
    )

    return redirect(url_for("admin"))


@app.route("/admin/mangas/<manga_id>/edit", methods=["GET"])
@login_required
def edit_manga_form(manga_id):
    manga = mangadb.get_manga_edit_data(manga_id)
    if manga is None:
        abort(404)
    return render_template(
        "admin_edit_manga.html", manga=manga, groups=mangadb.get_groups(),
        statuses=mangadb.MANGA_STATUSES, tag_groups=mangadb.TAG_GROUPS,
        sensitive_tags=mangadb.SENSITIVE_TAGS, error=None,
    )


@app.route("/admin/mangas/<manga_id>/edit", methods=["POST"])
@login_required
def update_manga(manga_id):
    manga = mangadb.get_manga_edit_data(manga_id)
    if manga is None:
        abort(404)
    try:
        mangadb.update_manga(
            manga_id,
            title=request.form.get("title"),
            synopsis=request.form.get("synopsis"),
            status=request.form.get("status"),
            tags=",".join(request.form.getlist("tags")),
            author=request.form.get("author"),
            group_id=request.form.get("group_id"),
            title_original=request.form.get("title_original"),
            artist=request.form.get("artist"),
            year=request.form.get("year"),
            rating=request.form.get("rating"),
        )
    except mangadb.ValidationError as e:
        return render_template(
            "admin_edit_manga.html", manga=manga, groups=mangadb.get_groups(),
            statuses=mangadb.MANGA_STATUSES, tag_groups=mangadb.TAG_GROUPS,
            sensitive_tags=mangadb.SENSITIVE_TAGS, error=str(e),
        ), 400

    new_title = request.form.get("title")
    if new_title != manga["title"]:
        rename_discord_role(mangadb.get_manga_discord_role(manga_id), new_title)

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

    cover_url = (request.form.get("cover_url") or "").strip()
    if not cover_url:
        return render_template(
            "admin_edit_cover.html",
            manga_id=manga_id, manga_title=title,
            current_cover=mangadb.static_url(mangadb.get_manga_cover(manga_id)),
            error="Selecione uma imagem.",
        ), 400

    mangadb.update_manga_cover(manga_id, cover_url)
    return redirect(url_for("admin"))


def delete_page_files_if_unshared(pages):
    """Apaga do disco local cada página cujo image_path não é usado por nenhuma outra
    página fora deste mesmo lote (protege dados de demonstração, que reaproveitam os
    mesmos arquivos entre capítulos). Exclui o próprio lote da contagem, senão apagar
    várias páginas que compartilham arquivo de uma vez (ex.: excluir o mangá inteiro)
    faria nenhuma delas ser apagada. Páginas hospedadas no R2 (`image_path` é uma URL
    http(s)) não são tocadas aqui - a limpeza delas acontece no navegador, via URL
    DELETE pré-assinada (`/admin/.../r2-delete-urls`), antes deste form ser enviado."""
    batch_ids = [p["id"] for p in pages]
    for p in pages:
        if is_r2_url(p["image_path"]):
            continue
        if mangadb.count_pages_with_image_path(p["image_path"], exclude_ids=batch_ids) == 0:
            full_path = os.path.join(app.root_path, "static", *p["image_path"].split("/"))
            if os.path.exists(full_path):
                os.remove(full_path)


@app.route("/admin/mangas/<manga_id>/delete", methods=["POST"])
@login_required
def delete_manga_route(manga_id):
    if mangadb.get_manga_title(manga_id) is None:
        abort(404)

    pages = mangadb.get_manga_pages_with_paths(manga_id)
    cover = mangadb.get_manga_cover(manga_id)
    role_id = mangadb.get_manga_discord_role(manga_id)

    delete_page_files_if_unshared(pages)
    if cover and not is_r2_url(cover):
        cover_full_path = os.path.join(app.root_path, "static", *cover.split("/"))
        if os.path.exists(cover_full_path):
            os.remove(cover_full_path)

    mangadb.delete_manga(manga_id)
    delete_discord_role(role_id)

    shutil.rmtree(
        os.path.join(app.root_path, "static", "assets", "pages", manga_id),
        ignore_errors=True,
    )

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
        today=date.today().isoformat(),
        error=None,
    )


def _parse_page_urls(raw_json, allow_empty=False):
    """Valida um campo oculto JSON (lista de {url, size}, montado pelo JS depois de
    cada arquivo já ter sido enviado direto pro R2). Devolve uma lista de
    (url, size_bytes) ou levanta ValueError com uma mensagem pro usuário."""
    try:
        items = json.loads(raw_json or "[]")
    except (TypeError, ValueError):
        raise ValueError("Não foi possível ler as páginas enviadas.")
    if not isinstance(items, list):
        raise ValueError("Não foi possível ler as páginas enviadas.")
    if not items and not allow_empty:
        raise ValueError("Selecione ao menos uma imagem de página.")

    pages = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Não foi possível ler as páginas enviadas.")
        url = item.get("url")
        if not is_r2_url(url):
            raise ValueError("Não foi possível ler as páginas enviadas.")
        size = item.get("size")
        size_bytes = int(size) if isinstance(size, (int, float)) else None
        pages.append((url, size_bytes))
    return pages


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
            today=date.today().isoformat(),
            error=message,
        ), status

    try:
        number_val, title, release_date = mangadb.validate_chapter_fields(
            request.form.get("number"), request.form.get("title"),
            request.form.get("release_date"), manga_id,
        )
    except mangadb.ValidationError as e:
        return render_error(str(e))

    try:
        pages = _parse_page_urls(request.form.get("page_urls"))
    except ValueError as e:
        return render_error(str(e))

    chapter_id = mangadb.build_chapter_id(manga_id, number_val)

    try:
        mangadb.add_chapter(
            manga_id=manga_id, chapter_id=chapter_id, number_val=number_val, title=title,
            release_date=release_date, pages=pages,
        )
    except mangadb.ValidationError as e:
        return render_error(str(e))

    notify_discord(
        title=f"🆕 {manga_title} — Cap. {mangadb.format_number(number_val)}",
        url=absolute_url(url_for("reader_page")) + f"?id={manga_id}&ch={chapter_id}",
        description=title,
        cover=mangadb.static_url(mangadb.get_manga_cover(manga_id)),
        role_id=mangadb.get_manga_discord_role(manga_id),
        synopsis=mangadb.get_manga_synopsis(manga_id),
    )

    return redirect(url_for("admin"))


@app.route("/admin/mangas/<manga_id>/chapters/bulk", methods=["GET"])
@login_required
def bulk_chapters_form(manga_id):
    title = mangadb.get_manga_title(manga_id)
    if title is None:
        abort(404)
    return render_template(
        "admin_bulk_chapters.html",
        manga_id=manga_id, manga_title=title, today=date.today().isoformat(),
    )


@app.route("/admin/mangas/<manga_id>/chapters/bulk-create", methods=["POST"])
@login_required
def bulk_create_chapter(manga_id):
    """Cria um único capítulo a partir de páginas já enviadas pro R2 - a mesma
    validação de sempre (mangadb.validate_chapter_fields), só que respondendo
    em JSON em vez de redirecionar, pra ser chamada repetidamente pelo JS do
    upload em massa (uma vez por .zip) sem navegar a página a cada capítulo."""
    manga_title = mangadb.get_manga_title(manga_id)
    if manga_title is None:
        abort(404)

    data = request.get_json(silent=True) or {}

    try:
        number_val, title, release_date = mangadb.validate_chapter_fields(
            data.get("number"), data.get("title"), data.get("release_date"), manga_id,
        )
    except mangadb.ValidationError as e:
        return jsonify({"error": str(e)}), 400

    pages_raw = data.get("pages")
    try:
        pages = _parse_page_urls(json.dumps(pages_raw) if pages_raw is not None else None)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    chapter_id = mangadb.build_chapter_id(manga_id, number_val)
    try:
        mangadb.add_chapter(
            manga_id=manga_id, chapter_id=chapter_id, number_val=number_val, title=title,
            release_date=release_date, pages=pages,
        )
    except mangadb.ValidationError as e:
        return jsonify({"error": str(e)}), 400

    notify_discord(
        title=f"🆕 {manga_title} — Cap. {mangadb.format_number(number_val)}",
        url=absolute_url(url_for("reader_page")) + f"?id={manga_id}&ch={chapter_id}",
        description=title,
        cover=mangadb.static_url(mangadb.get_manga_cover(manga_id)),
        role_id=mangadb.get_manga_discord_role(manga_id),
        synopsis=mangadb.get_manga_synopsis(manga_id),
    )

    return jsonify({"ok": True, "chapter_id": chapter_id})


@app.route("/admin/mangas/<manga_id>/chapters", methods=["GET"])
@login_required
def chapters_list(manga_id):
    title = mangadb.get_manga_title(manga_id)
    if title is None:
        abort(404)
    return render_template(
        "admin_chapters.html",
        manga_id=manga_id, manga_title=title,
        chapters=mangadb.get_manga_chapters(manga_id),
    )


def render_edit_chapter(manga_id, manga_title, chapter, error=None, status=200):
    pages = [{**p, "url": mangadb.static_url(p["image_path"])} for p in chapter["pages"]]
    return render_template(
        "admin_edit_chapter.html",
        manga_id=manga_id, manga_title=manga_title, chapter=chapter, pages=pages, error=error,
    ), status


@app.route("/admin/mangas/<manga_id>/chapters/<chapter_id>/edit", methods=["GET"])
@login_required
def edit_chapter_form(manga_id, chapter_id):
    chapter = mangadb.get_chapter_edit_data(manga_id, chapter_id)
    if chapter is None:
        abort(404)
    return render_edit_chapter(manga_id, mangadb.get_manga_title(manga_id), chapter)


@app.route("/admin/mangas/<manga_id>/chapters/<chapter_id>/edit", methods=["POST"])
@login_required
def update_chapter(manga_id, chapter_id):
    chapter = mangadb.get_chapter_edit_data(manga_id, chapter_id)
    if chapter is None:
        abort(404)
    manga_title = mangadb.get_manga_title(manga_id)

    def reject(message, status=400):
        return render_edit_chapter(manga_id, manga_title, chapter, error=message, status=status)

    try:
        number_val, title, release_date = mangadb.validate_chapter_fields(
            request.form.get("number"), request.form.get("title"),
            request.form.get("release_date"), manga_id, exclude_chapter_id=chapter_id,
        )
    except mangadb.ValidationError as e:
        return reject(str(e))

    try:
        new_pages = _parse_page_urls(request.form.get("new_pages"), allow_empty=True)
    except ValueError as e:
        return reject(str(e))

    existing_ids = {p["id"] for p in chapter["pages"]}

    # -- interpreta e valida o `order` montado pelo JS, sem confiar em nada do cliente --
    tokens = [t for t in (request.form.get("order") or "").split(",") if t]
    seen_existing = set()
    seen_new = set()
    final_entries = []  # ("existing", page_id) ou ("new", índice em new_pages)
    for tok in tokens:
        kind, raw = tok[0], tok[1:]
        if kind == "e":
            if not raw.isdigit() or int(raw) not in existing_ids or int(raw) in seen_existing:
                return reject("Ordem de páginas inválida.")
            pid = int(raw)
            seen_existing.add(pid)
            final_entries.append(("existing", pid))
        elif kind == "n":
            if not raw.isdigit() or int(raw) >= len(new_pages) or int(raw) in seen_new:
                return reject("Ordem de páginas inválida.")
            idx = int(raw)
            seen_new.add(idx)
            final_entries.append(("new", idx))
        else:
            return reject("Ordem de páginas inválida.")

    if not final_entries:
        return reject("O capítulo precisa de pelo menos uma página.")

    removed_ids = [p["id"] for p in chapter["pages"] if p["id"] not in seen_existing]
    removed_pages = mangadb.get_pages_by_ids(removed_ids)

    mangadb.update_chapter_metadata(chapter_id, number_val, title, release_date)

    delete_page_files_if_unshared(removed_pages)
    mangadb.delete_pages_by_ids(removed_ids)

    for position, (kind, ref) in enumerate(final_entries):
        if kind == "existing":
            mangadb.set_page_position(ref, position)
        else:
            url, size_bytes = new_pages[ref]
            mangadb.insert_page(chapter_id, position, url, size_bytes)

    return redirect(url_for("chapters_list", manga_id=manga_id))


@app.route("/admin/mangas/<manga_id>/chapters/<chapter_id>/delete", methods=["POST"])
@login_required
def delete_chapter_route(manga_id, chapter_id):
    chapter = mangadb.get_chapter_edit_data(manga_id, chapter_id)
    if chapter is None:
        abort(404)

    delete_page_files_if_unshared(chapter["pages"])
    mangadb.delete_chapter(chapter_id)

    shutil.rmtree(
        os.path.join(app.root_path, "static", "assets", "pages", manga_id, chapter_id),
        ignore_errors=True,
    )

    return redirect(url_for("chapters_list", manga_id=manga_id))


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Página não encontrada."), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.exception("Erro interno não tratado")
    return render_template("error.html", code=500, message="Algo deu errado do nosso lado. Já estamos cientes."), 500


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
