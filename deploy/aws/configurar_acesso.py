"""Salva segredos localmente, sem exibi-los e sem acessar a AWS."""
import getpass
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    destino = ROOT / '.deploy' / 'aws-secrets.json'
    if destino.exists():
        raise SystemExit('O arquivo privado já existe. Revise-o antes de substituir.')
    chave = os.getenv('OPENAI_API_KEY') or getpass.getpass('Chave secreta OpenAI (entrada oculta): ')
    if not chave.strip():
        raise SystemExit('Chave vazia. Nenhum arquivo criado.')
    dados = {'OPENAI_API_KEY': chave.strip()}
    destino.parent.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as arquivo:
        json.dump(dados, arquivo, indent=2)
        arquivo.write('\n')
    print('Configuração privada salva em .deploy/aws-secrets.json (permissão 600, ignorado pelo Git).')
    print('Nenhuma chave exibida. Nenhum dado enviado à AWS. Avise no chat que configurou.')


if __name__ == '__main__':
    main()
