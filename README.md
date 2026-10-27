# PoC de organização financeira

Configure a chave na variável de ambiente, sem incluí-la no código:

```sh
export OPENAI_API_KEY="SUA_CHAVE_OPENAI"
```

Com o ambiente virtual existente e suas dependências instaladas:

```sh
cd assistente-organizacao-financeira
../.venv/bin/python agent.py
../.venv/bin/python evals.py
```

O modelo configurado é `gpt-6-luna`. As avaliações com modelos exigem acesso à API.
Pagamentos solicitados pelo agente exigem aprovação humana no terminal.
A sessão SQLite é criada em `conversas_financeiras.db` no diretório de execução.
Arquivos locais de sessão e credenciais são ignorados pelo Git.

## Arquitetura

![Arquitetura do assistente financeiro: usuário, agente, ferramentas, dados simulados, aprovação humana e observabilidade](assistente-organizacao-financeira/arquitetura_assistente_financeiro.png)

O fluxo segue quatro blocos: **usuário → agente → ferramentas → dados simulados**.
O LLM interpreta a solicitação e escolhe ferramentas; o OpenAI Agents SDK controla
sua execução. Para pagamentos, o SDK interrompe o fluxo antes de executar a
ferramenta e aguarda a decisão humana no terminal.

### Diagrama em Mermaid

A versão abaixo acompanha a organização e as cores da imagem: interação em roxo,
agente em azul, ferramentas em verde, pagamento em vermelho e simulação em âmbar.

```mermaid
flowchart LR
    subgraph UI["USUÁRIO"]
        direction TB
        CLI["Terminal · CLI<br/><br/>Qual é meu saldo?<br/>Quais boletos estão pendentes?<br/>Monte um plano de pagamentos.<br/>Pague meu boleto de energia."]
    end

    subgraph AGENT["AGENTE · OpenAI Agents SDK"]
        direction TB
        LLM["LLM · gpt-6-luna<br/>Interpretação e escolha de ferramentas"]
        SDK["Runner · Execução e retomada<br/>Coordena ferramentas e interrupções"]
        INSTRUCTIONS["Instruções do agente<br/>Quando usar ferramentas<br/>e como responder"]
        CONTEXT["ContextoFinanceiro<br/>Contador e limite de buscas"]
        SESSION["Memória de conversa<br/>SQLiteSession"]
        LLM <--> SDK
        INSTRUCTIONS -.-> LLM
        CONTEXT -.-> SDK
        SESSION -.- SDK
    end

    subgraph TOOLS["FERRAMENTAS · Python"]
        direction TB
        QUERIES["Consultar e buscar<br/><br/>consultar_saldo<br/>consultar_limite_cartao<br/>buscar_boletos<br/>listar_boletos_pendentes"]
        PLAN["Planejar<br/>gerar_plano_pagamentos"]
        PAY["Pagamento protegido<br/>pagar_boleto<br/>needs_approval=True"]
    end

    subgraph BACKEND["DADOS E REGRAS · Simulação"]
        direction TB
        RULES["Backend fake · financeiro.py<br/>Planejamento por vencimento<br/>Validação de saldo e duplicidade<br/>Pagamento simulado"]
        DATA[("Dados simulados<br/>Saldo · limite · boletos<br/>Pagamentos realizados")]
        RULES <--> DATA
    end

    HUMAN["APROVAÇÃO HUMANA · HITL<br/>Usuário autoriza ou rejeita no terminal<br/>O Runner retoma com a decisão"]

    subgraph OBS["OBSERVABILIDADE E AVALIAÇÃO"]
        direction LR
        TRACE["Tracing · OpenAI Traces<br/>Chamadas ao LLM e às ferramentas<br/>Inputs, outputs e duração"]
        EVAL["Evals · evals.py<br/>Ferramentas · HITL · rejeição · duplicidade<br/>Answer Quality · LLM-as-a-Judge"]
    end

    CLI -->|1 · Pergunta| SDK
    SDK -->|2 · Seleciona e chama| QUERIES
    SDK -->|2 · Seleciona e chama| PLAN
    SDK -->|2 · Solicita pagamento| PAY
    PAY -->|3 · Interrompe e solicita aprovação| HUMAN
    HUMAN -.->|4 · Aprova ou rejeita| PAY
    QUERIES <--> DATA
    PLAN <--> RULES
    PAY -->|Executa somente se aprovado| RULES
    TOOLS -.->|5 · Resultado ou rejeição| SDK
    SDK -.->|6 · Resposta ao usuário| CLI
    SDK -.->|Logs e traces| TRACE
    EVAL -.->|Avalia comportamento e segurança| SDK

    classDef user fill:#f5f3ff,stroke:#c4b5fd,color:#312e81,stroke-width:1.5px
    classDef llm fill:#2864b4,stroke:#1e40af,color:#ffffff,stroke-width:2px
    classDef agent fill:#eaf4ff,stroke:#93c5fd,color:#172554,stroke-width:1.5px
    classDef tool fill:#dcf5e5,stroke:#86d5a5,color:#14532d,stroke-width:1.5px
    classDef payment fill:#ffe5e5,stroke:#fca5a5,color:#7f1d1d,stroke-width:2px
    classDef simulation fill:#fff4dd,stroke:#fbbf24,color:#78350f,stroke-width:1.5px
    classDef trace fill:#f5eafd,stroke:#d8b4fe,color:#581c87,stroke-width:1.5px
    class CLI user
    class LLM llm
    class SDK,INSTRUCTIONS,CONTEXT,SESSION agent
    class QUERIES,PLAN,EVAL tool
    class PAY payment
    class RULES,DATA,HUMAN simulation
    class TRACE trace
    style UI fill:#faf8ff,stroke:#ddd6fe,stroke-width:2px
    style AGENT fill:#f0f7ff,stroke:#93c5fd,stroke-width:2px
    style TOOLS fill:#f0faf4,stroke:#a7dcbc,stroke-width:2px
    style BACKEND fill:#fffaf0,stroke:#fdba74,stroke-width:2px,stroke-dasharray:6 4
    style OBS fill:#fafafa,stroke:#94a3b8,stroke-width:1.5px,stroke-dasharray:6 4
```

**Aprovação:** autorizar retoma o Runner e permite executar `pagar_boleto`.
Rejeitar retoma a conversa sem executar o pagamento. O LLM não autoriza a operação.

**Backend substituível:** os dados e as regras simulados rodam no mesmo processo
Python. O limite do cartão e algumas consultas são valores fixos nas ferramentas;
o saldo e os pagamentos realizados são mantidos em memória em `financeiro.py`.
A integração futura com serviços reais acontecerá pelas ferramentas.

**Memória:** o SQLite armazena o histórico da conversa, não o estado financeiro.
O tracing acompanha a interação, incluindo a interrupção e a retomada do HITL.

### Onde cada parte está no código

| Parte do desenho | Implementação atual |
| --- | --- |
| Interação | `agent.py` inicia `terminal.py`; `hitl.py` coleta a decisão humana |
| Agente e LLM | `configuracao.py` define modelo, instruções e ferramentas; `ContextoFinanceiro.py` mantém o contexto |
| Ferramentas | `ferramentas.py` adapta as operações para o SDK |
| Backend fake | `financeiro.py` contém estado e regras; algumas consultas fixas ainda estão em `ferramentas.py` |
| Memória | `SQLiteSession` mantém o histórico, separado do estado financeiro em memória |
| Observabilidade | `terminal.py` cria um trace por interação, incluindo execução e retomada |
| Avaliações | `evals.py` verifica ferramentas, HITL, rejeição, duplicidade, Answer Quality e LLM-as-a-Judge |

**Futura integração:** substituir os dados e operações simulados por chamadas a
serviços reais, mantendo as ferramentas como ponto de integração. O backend fake
é uma separação lógica: hoje ele roda no mesmo processo Python, sem servidor HTTP
ou banco transacional.

## Organização

- `agent.py`: entrada e compatibilidade dos imports existentes.
- `configuracao.py`: agentes, instruções, modelo e ferramentas habilitadas.
- `financeiro.py`: estado e regras financeiras simuladas, sem SDK.
- `ferramentas.py`: adaptação das operações para ferramentas do SDK.
- `ContextoFinanceiro.py`: contexto e exceção de limite de buscas.
- `terminal.py`: terminal, sessão, tracing e tratamento de erros.
- `hitl.py`: decisão humana e retomada das interrupções.
- `evals.py`: avaliações comportamentais, de segurança e de qualidade.
- `example.py`: exemplo independente da API Responses.

## Validação local

Sem credenciais e sem chamadas à API:

```sh
.venv/bin/python -m unittest discover -s assistente-organizacao-financeira/tests -v
```

Os testes verificam planejamento, duplicidade, início pelo terminal e interrupção/rejeição
HITL usando o Runner do SDK, um modelo local controlado e SQLite temporário.
Nenhum pagamento é aprovado automaticamente. Isso não substitui as avaliações com modelos.

O comportamento preexistente para identificadores inexistentes em
`executar_pagamento_simulado` foi preservado: a ausência do boleto pode causar erro.
