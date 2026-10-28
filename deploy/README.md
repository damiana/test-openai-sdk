# Configuração e validação da demonstração

Para iniciar os dois servidores e testar a aplicação pública, consulte o
[README principal](../README.md). Para publicar, consulte o [guia AWS](aws/README.md).

## Sessões e segurança

O browser solicita `POST /session` e recebe token aleatório, mantido somente na
memória da página. Cada sessão recebe saldo de R$ 350,00 e boletos próprios.
O backend exige `Authorization: Bearer ...`, valida a propriedade das conversas e
serializa requisições da mesma sessão até o fim do streaming SSE.
O código de acesso compartilhado protege a entrada da demonstração; não é login
corporativo. Compartilhar apenas com os participantes autorizados, fora do Git.
CORS e domainKey não são autenticação. Não usar dados pessoais na demonstração.

Limites locais: 50 sessões, 20 novas sessões/minuto, 2 horas por sessão,
60 solicitações/minuto e 300 solicitações totais por sessão, corpo de até 256 KiB.
Os limites são por processo e não constituem proteção contra ataques distribuídos.

SQLiteSession continua em memória, como no ChatKit original. Conversas, contexto,
aprovações e finanças se perdem ao reiniciar. Atualizar a página cria nova sessão.
O frontend exige iniciar novamente após um token inválido; nunca repete uma
aprovação automaticamente. Não configurar múltiplos workers ou scale-out.

Se uma retomada falhar, a decisão é consumida e não é repetida automaticamente.
Consulte saldo e boletos antes de solicitar outra operação. Duplicidade continua
validada pela regra financeira; em caso de restart, toda a simulação é restaurada.

## Executar localmente

Da raiz do projeto, exportar `OPENAI_API_KEY` no seu terminal. Nunca colar a chave
no código, no frontend ou em arquivos versionados.

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn api:app --app-dir test-ui --port 8000
```

Em outro terminal:

```sh
cd test-ui/frontend
npm ci
npm run dev
```

Opcionalmente exportar `DEMO_ACCESS_CODE` no backend para testar a tela de entrada.
Os `.env.example` documentam variáveis. O backend usa o ambiente do processo e não
carrega `.env` automaticamente. O Vite carrega seu próprio `.env.local`.

## Validar antes de publicar

```sh
PYTHONPATH=assistente-organizacao-financeira .venv/bin/python -m unittest discover -s assistente-organizacao-financeira/tests -v
PYTHONPATH=assistente-organizacao-financeira:test-ui .venv/bin/python -m unittest discover -s test-ui/tests -v
```

Os arquivos `test_pagamentos.py`, `test_hitl.py` e `test_avaliar_agente.py` também
contêm runners próprios; a descoberta unittest não executa suas funções soltas.
Os testes novos exercitam protocolo HTTP, autorização, isolamento em tasks/threads,
streaming SSE, widgets, rejeição e reenvio do HITL sem aprovar automaticamente.
As avaliações LLM exigem a chave OpenAI. O runner integral de `evals.py` e
`test_hitl.py` contém aprovação automática; não executá-lo neste fluxo de publicação.
Executar as avaliações sem aprovação por funções selecionadas; validar aprovação
pela interface com decisão humana.

