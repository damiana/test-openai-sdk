# Configuração e validação da demonstração

Para iniciar os dois servidores e testar a aplicação pública, consulte o
[README principal](../README.md). Para publicar, consulte o [guia AWS](aws/README.md).

## Sessões e segurança

O browser solicita `POST /session` e recebe token aleatório, mantido somente na
memória da página. Cada sessão recebe saldo de R$ 350,00 e boletos próprios.
O backend exige `Authorization: Bearer ...`, valida a propriedade das conversas e
serializa requisições da mesma sessão até o fim do streaming SSE.
A criação de sessão é anônima e não exige código de entrada. O token identifica
a sessão e separa as conversas; não autentica uma pessoa. Qualquer visitante pode
iniciar uma demonstração e consumir a API dentro dos limites configurados.
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

## Ambiente local

Os comandos de instalação, backend e frontend estão no
[README principal](../README.md#como-executar-localmente).
O backend lê as variáveis do processo e não carrega `.env` automaticamente;
o Vite carrega `test-ui/frontend/.env.local`. Consulte os exemplos de variáveis
[do backend](../.env.example) e [do frontend](../test-ui/frontend/.env.example).

Se houver um `.env.local` de outro ambiente, confira se `VITE_CHATKIT_API_URL`
aponta para `http://localhost:8000/chatkit` e reinicie o Vite após alterar.
A origem autorizada por padrão é `http://localhost:5173`; hostname ou porta
diferentes exigem ajuste em `CORS_ORIGINS` antes de iniciar o backend.
O argumento `--app-dir test-ui` permite importar `api` quando o comando parte da raiz.

## Executar pelo terminal, sem interface web

Com o ambiente virtual instalado e `OPENAI_API_KEY` exportada, partindo da raiz:

```sh
cd assistente-organizacao-financeira
../.venv/bin/python agent.py
```

Esse modo não exige os servidores web. A decisão HITL é feita no terminal.
O histórico é salvo em `conversas_financeiras.db` no diretório de execução;
o saldo continua sendo simulado em memória. Arquivos locais de sessão e
credenciais são ignorados pelo Git. Esse SQLite em arquivo é específico da CLI;
na interface web, o histórico SQLite permanece em memória.

## Validar antes de publicar

Execute os comandos da [seção Testes](../README.md#testes).
Os arquivos `test_pagamentos.py`, `test_hitl.py` e `test_avaliar_agente.py` têm
runners próprios; a descoberta unittest não executa suas funções soltas.
O cenário de aprovação exige `--aprovacao-manual` em `evals.py` ou
`tests/test_hitl.py` e decisão humana no terminal. Não há aprovação automática.

O [guia de arquitetura](../docs/arquitetura.md) detalha o funcionamento, as avaliações
e as limitações do projeto. O [roteiro de demonstração](../docs/demonstracao.md)
orienta a validação manual dos widgets e pagamentos.
