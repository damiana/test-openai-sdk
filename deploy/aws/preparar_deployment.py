"""Gera JSON privado do deploy Lightsail sem criar ou publicar recursos."""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='URL HTTPS retornada pelo Lightsail')
    parser.add_argument('--image', required=True, help='Referência privada retornada por push-container-image')
    parser.add_argument('--domain-key', required=True, help='domainKey público cadastrado no ChatKit')
    args = parser.parse_args()
    url = urlparse(args.url)
    if url.scheme != 'https' or not url.netloc or url.path not in ('', '/') or url.query or url.fragment or url.username:
        parser.error('--url deve ser a origem HTTPS, sem caminho, credenciais ou parâmetros.')
    if args.domain_key == 'local-dev':
        parser.error('Cadastre a URL pública no ChatKit e informe o domainKey correspondente.')
    if not args.image.startswith(':'):
        parser.error('Use a referência privada do Lightsail retornada pelo push-container-image.')
    output = ROOT / '.deploy' / 'aws-deployment.json'
    code_path = ROOT / '.deploy' / 'aws-demo-access-code.txt'
    if output.exists() or code_path.exists():
        raise SystemExit('Arquivos privados já existem. Revise-os antes de substituir um deployment.')
    secrets_path = ROOT / '.deploy' / 'aws-secrets.json'
    private = json.loads(secrets_path.read_text()) if secrets_path.is_file() else {}
    key = private.get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY') or getpass.getpass('Chave OpenAI (entrada oculta): ')
    if not key.strip():
        raise SystemExit('Chave não informada. Nenhum arquivo criado.')
    code = private.get('DEMO_ACCESS_CODE') or secrets.token_urlsafe(24)
    origin = f'{url.scheme}://{url.netloc}'
    data = {
        'containers': {'finai': {
            'image': args.image,
            'ports': {'8000': 'HTTP'},
            'environment': {
                'APP_ENV': 'production', 'CORS_ORIGINS': origin,
                'PUBLIC_CHATKIT_API_URL': '/chatkit', 'CHATKIT_DOMAIN_KEY': args.domain_key,
                'OPENAI_API_KEY': key.strip(), 'DEMO_ACCESS_CODE': code,
            },
        }},
        'publicEndpoint': {'containerName': 'finai', 'containerPort': 8000, 'healthCheck': {
            'path': '/health', 'successCodes': '200', 'intervalSeconds': 15,
            'timeoutSeconds': 5, 'healthyThreshold': 2, 'unhealthyThreshold': 3,
        }},
    }
    output.parent.mkdir(mode=0o700, exist_ok=True)
    for path, text in [(output, json.dumps(data, indent=2) + '\n'), (code_path, code + '\n')]:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as file:
            file.write(text)
    print('Preparados .deploy/aws-deployment.json e .deploy/aws-demo-access-code.txt, com permissão 600.')
    print('Contêm segredos. Não enviar ao Git ou ao chat. Nenhum recurso foi criado.')


if __name__ == '__main__':
    main()
