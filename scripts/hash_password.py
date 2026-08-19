"""
Gera o hash de senha para a variável de ambiente ADMIN_PASSWORD_HASH.
Uso: python scripts/hash_password.py
Digite a senha quando solicitado; copie o hash impresso para a config
de variáveis de ambiente do host (nunca cole a senha em texto puro em lugar nenhum).
"""
import getpass
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash


def main():
    password = getpass.getpass("Senha do admin: ")
    confirm = getpass.getpass("Confirme a senha: ")
    if password != confirm:
        print("As senhas não coincidem.", file=sys.stderr)
        sys.exit(1)
    print(generate_password_hash(password))


if __name__ == "__main__":
    main()
