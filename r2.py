"""
Assinatura de URLs pré-assinadas (SigV4) pro bucket R2, na mão - sem boto3/botocore
(que adicionam ~70-100MB ao venv, caro demais pra cota de disco de 512MB do
PythonAnywhere free tier). Presign é só HMAC local, não faz nenhuma chamada de
rede - por isso funciona mesmo com o bloqueio de saída do free tier. O Flask
nunca fala com o R2 diretamente: só assina URLs que o navegador do admin usa.

Variáveis de ambiente lidas sob demanda (não na importação), pra não derrubar
o app inteiro se o R2 ainda não foi configurado - só as rotas que dependem
delas falham, com uma mensagem clara.
"""
import hashlib
import hmac
import os
from datetime import datetime, timezone
from urllib.parse import quote

REGION = "auto"
SERVICE = "s3"

CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
}


class R2NotConfigured(Exception):
    pass


def _env(name):
    value = os.environ.get(name)
    if not value:
        raise R2NotConfigured(f"Variável de ambiente {name} não configurada.")
    return value


def _config():
    return {
        "account_id": _env("R2_ACCOUNT_ID"),
        "access_key": _env("R2_ACCESS_KEY_ID"),
        "secret_key": _env("R2_SECRET_ACCESS_KEY"),
        "bucket": _env("R2_BUCKET_NAME"),
        "public_base_url": _env("R2_PUBLIC_BASE_URL"),
    }


def sniff_bytes(head):
    """Identifica o tipo real da imagem pelos bytes (assinatura mágica), nunca
    pelo nome/Content-Type declarado pelo cliente - mesma lógica que existia
    antes em app.py, agora operando sobre bytes crus (só os primeiros ~16)
    em vez de um FileStorage, já que o arquivo inteiro não passa mais pelo Flask."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def public_url(key):
    cfg = _config()
    return f"{cfg['public_base_url'].rstrip('/')}/{key}"


def key_from_public_url(url):
    """Devolve a key do objeto se `url` for hospedada no nosso bucket R2, ou
    None caso contrário (ex.: caminho local legado tipo 'assets/covers/x.png')."""
    if not url:
        return None
    try:
        cfg = _config()
    except R2NotConfigured:
        return None
    base = cfg["public_base_url"].rstrip("/") + "/"
    if not url.startswith(base):
        return None
    return url[len(base):]


def _sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key, date_stamp, region, service):
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def sign_request(method, host, canonical_uri, query_params, amz_date, date_stamp,
                  access_key, secret_key, region, service, extra_headers=None):
    """Núcleo puro do SigV4 (sem env vars/tempo real) - separado de `_presign` só
    pra poder ser testado contra o vetor de teste oficial da AWS
    (scripts/test_r2_sigv4.py), sem depender de credenciais reais nem do
    relógio do sistema. Devolve (canonical_request, string_to_sign, signature).
    `extra_headers` (dict, nomes em minúsculo) entra assinado além de `host` -
    ex.: content-type, pra travar o presign PUT num tipo de arquivo específico.
    Opcional e por padrão vazio, então o vetor de teste da AWS (que só assina
    `host`) continua batendo sem mudança."""
    headers = {"host": host, **(extra_headers or {})}
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    canonical_querystring = "&".join(
        f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in sorted(query_params.items())
    )
    canonical_headers = "".join(f"{k}:{v}\n" for k, v in sorted(headers.items()))
    signed_headers = ";".join(sorted(headers))
    payload_hash = "UNSIGNED-PAYLOAD"

    canonical_request = "\n".join([
        method, canonical_uri, canonical_querystring,
        canonical_headers, signed_headers, payload_hash,
    ])
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])
    signing_key = _signing_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return canonical_request, string_to_sign, signature


def _presign(method, key, expires_seconds, extra_headers=None):
    cfg = _config()
    host = f"{cfg['account_id']}.r2.cloudflarestorage.com"
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    credential_scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"

    canonical_uri = "/" + quote(f"{cfg['bucket']}/{key}", safe="/-_.~")
    signed_header_names = ";".join(sorted({"host", *(extra_headers or {})}))
    query_params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{cfg['access_key']}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires_seconds),
        "X-Amz-SignedHeaders": signed_header_names,
    }
    _, _, signature = sign_request(
        method, host, canonical_uri, query_params, amz_date, date_stamp,
        cfg["access_key"], cfg["secret_key"], REGION, SERVICE, extra_headers=extra_headers,
    )
    canonical_querystring = "&".join(
        f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in sorted(query_params.items())
    )
    return f"https://{host}{canonical_uri}?{canonical_querystring}&X-Amz-Signature={signature}"


def presign_put(key, content_type, expires_seconds=600):
    """Content-Type entra no conjunto de headers assinados - a URL só serve
    pra subir um arquivo com exatamente esse Content-Type, então mesmo que a
    URL vaze ela não pode ser reaproveitada pra subir outro tipo de conteúdo
    na mesma key. O navegador já manda esse mesmo header no PUT real
    (sniffAndPresign em admin_uploads.js), então não muda nada pro fluxo normal."""
    return _presign("PUT", key, expires_seconds, extra_headers={"content-type": content_type})


def presign_delete(key, expires_seconds=600):
    return _presign("DELETE", key, expires_seconds)
