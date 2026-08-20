"""
Confere a implementação de assinatura SigV4 em r2.py contra o vetor de teste
oficial publicado pela AWS (docs "Authenticating Requests: Using Query
Parameters (AWS Signature Version 4)", exemplo "GET Object"), independente de
qualquer credencial real do R2 ou do relógio do sistema - só valida que a
matemática da assinatura está certa.
Uso: python scripts/test_r2_sigv4.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from r2 import sign_request

ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
HOST = "examplebucket.s3.amazonaws.com"
CANONICAL_URI = "/test.txt"
AMZ_DATE = "20130524T000000Z"
DATE_STAMP = "20130524"
REGION = "us-east-1"
SERVICE = "s3"

QUERY_PARAMS = {
    "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
    "X-Amz-Credential": f"{ACCESS_KEY}/{DATE_STAMP}/{REGION}/{SERVICE}/aws4_request",
    "X-Amz-Date": AMZ_DATE,
    "X-Amz-Expires": "86400",
    "X-Amz-SignedHeaders": "host",
}

EXPECTED_SIGNATURE = "aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"


def main():
    _, _, signature = sign_request(
        "GET", HOST, CANONICAL_URI, QUERY_PARAMS, AMZ_DATE, DATE_STAMP,
        ACCESS_KEY, SECRET_KEY, REGION, SERVICE,
    )
    if signature != EXPECTED_SIGNATURE:
        print("FALHOU")
        print(f"  esperado: {EXPECTED_SIGNATURE}")
        print(f"  obtido:   {signature}")
        print("  Se isso não bater, re-confira contra o exemplo 'GET Object' na")
        print("  documentação da AWS antes de confiar em qualquer URL assinada por r2.py.")
        sys.exit(1)
    print("OK - assinatura bate com o vetor de teste oficial da AWS.")


if __name__ == "__main__":
    main()
