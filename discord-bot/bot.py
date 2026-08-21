import hmac
import json
import os
import urllib.error
import urllib.request

from flask import Flask, abort, jsonify, request

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_GUILD_ID = os.environ["DISCORD_GUILD_ID"]
BOT_INTERNAL_SECRET = os.environ["BOT_INTERNAL_SECRET"]

DISCORD_API = "https://discord.com/api/v10"

app = Flask(__name__)


def discord_request(method, path, body=None):
    """Chamada crua na API REST do Discord - só precisa do token do bot, sem
    conexão de gateway (não há comando por mensagem/slash nessa v1, só criação
    de cargo sob demanda), o que deixa esse serviço sem estado nenhum."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        DISCORD_API + path, data=data, method=method,
        headers={
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "Content-Type": "application/json",
            # Sem isso o Cloudflare na frente do discord.com barra o request
            # (User-Agent genérico do urllib parece automação) com erro 1010.
            "User-Agent": "SukiBot (https://sukimangas.pythonanywhere.com, 1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def check_auth():
    """Compara o Bearer token com BOT_INTERNAL_SECRET em tempo constante - só o
    Suki (que sabe o segredo) pode mandar esse serviço criar cargo."""
    header = request.headers.get("Authorization", "")
    token = header[len("Bearer "):] if header.startswith("Bearer ") else ""
    if not hmac.compare_digest(token, BOT_INTERNAL_SECRET):
        abort(401)


@app.route("/")
def health():
    return jsonify({"ok": True})


@app.route("/roles", methods=["POST"])
def create_role():
    check_auth()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title é obrigatório"}), 400

    # Nome de cargo no Discord tem limite de 100 caracteres.
    role_name = title[:100]

    try:
        role = discord_request(
            "POST", f"/guilds/{DISCORD_GUILD_ID}/roles",
            {"name": role_name, "mentionable": True, "hoist": False},
        )
    except urllib.error.HTTPError as e:
        return jsonify({"error": f"discord respondeu {e.code}: {e.read().decode('utf-8', 'ignore')}"}), 502

    return jsonify({"role_id": role["id"]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
