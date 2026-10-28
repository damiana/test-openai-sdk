# Arquitetura e funcionamento

O Assistente Financeiro Inteligente combina interpretação de linguagem natural,
ferramentas Python e aprovação humana para consultar dados e executar pagamentos
simulados. O OpenAI Agents SDK coordena a execução; o ChatKit apresenta a conversa
e os cartões interativos.

![Arquitetura do Assistente Financeiro Inteligente](../imagens/arquitetura_assistente_financeiro.png)

## Componentes

| Componente | Responsabilidade | Arquivos principais |
| --- | --- | --- |
| React e ChatKit | Conversa, widgets e botões de aprovação | `test-ui/frontend/src/App.jsx` |
| FastAPI | Endpoints HTTP, sessão, limites e controle de concorrência | `test-ui/api.py`, `test-ui/sessoes_web.py` |
| ChatKit Server | Integração com o agente e apresentação dos resultados | `test-ui/servidor_chatkit.py` |
| Agente financeiro | Modelo, instruções, ferramentas e contrato de resposta | `assistente-organizacao-financeira/configuracao.py` |
| Ferramentas | Operações disponíveis ao agente | `assistente-organizacao-financeira/ferramentas.py` |
| Regras financeiras | Planejamento, validação de saldo, pagamento e duplicidade | `assistente-organizacao-financeira/financeiro.py` |
| Armazenamento da interface | Conversas, itens e verificação de proprietário | `test-ui/store_memoria.py` |

O modelo configurado é `gpt-6-luna`. As versões das bibliotecas estão em
[`requirements.txt`](../requirements.txt) e no
[`package.json`](../test-ui/frontend/package.json).

## Fluxo de uma solicitação

1. O navegador cria uma sessão anônima e recebe um token temporário.
2. O ChatKit envia a mensagem para o backend, que verifica a sessão e a conversa.
3. `simple_to_agent_input` converte a mensagem para o formato aceito pelo SDK.
4. O `Runner` executa o agente com o histórico e o contexto financeiro da sessão.
5. O modelo solicita as ferramentas necessárias; as funções Python consultam os
   dados simulados e aplicam as regras financeiras.
6. O servidor apresenta a resposta validada ou um widget com os dados da ferramenta.

A sessão mantém um lock durante toda a requisição, inclusive o streaming SSE,
para impedir operações simultâneas sobre o mesmo estado financeiro.

## Agente, contexto e histórico

`Agent` reúne instruções, ferramentas e `output_type=RespostaAgente`. O contrato
Pydantic distingue uma resposta de um pedido de esclarecimento e indica sua
visualização. Quando falta identificar o boleto, o agente pede essa informação
antes de solicitar o pagamento.

O `ContextoFinanceiro` transporta o estado financeiro e o contador de buscas por
`RunContextWrapper`. O limite é de duas buscas por solicitação. O contador reinicia
em uma nova mensagem e acompanha a mesma execução durante a retomada do HITL.
Esse contexto é uma dependência local das ferramentas, não uma mensagem ao modelo.

`SQLiteSession` guarda o histórico que permite referências a turnos anteriores.
Apenas a mensagem nova é convertida para entrada do Runner; o histórico é fornecido
pela sessão, sem ser reenviado também pelo Store do ChatKit.

## Aprovação humana de pagamentos

A ferramenta `pagar_boleto` usa `@function_tool(needs_approval=True)`. A solicitação
do modelo interrompe o Runner antes da execução financeira.

O servidor armazena o `RunState` e exibe um cartão associado à conversa, à chamada
e a um identificador de aprovação. Enquanto a decisão está pendente, novas mensagens
não iniciam outra execução naquela conversa.

- **Aprovar:** chama `state.approve(interrupcao)` e retoma o Runner.
- **Rejeitar:** chama `state.reject(interrupcao)` e retoma sem executar o pagamento.
- **Vários pagamentos:** cada cartão decide somente a operação exibida.
- **Clique repetido ou antigo:** o identificador deixa de ser válido após a decisão.

O cartão de aprovação é substituído pelo resultado. A autorização humana permite
a execução, mas não comprova sucesso:

| Resultado da ferramenta | Mensagem do cartão |
| --- | --- |
| `status=PAGO`, com o mesmo boleto da chamada | Pagamento realizado |
| `status=ERRO` | Pagamento não realizado |
| Resultado ausente, inesperado ou falha na retomada | Resultado não confirmado |

O resultado é associado pelo `call_id` da operação. Em caso de falha de retomada,
a decisão é consumida e não é reenviada automaticamente. A consulta de saldo e
boletos permite conferir o estado antes de tentar outra operação.

## Dados e regras financeiras

As funções financeiras são independentes do SDK. Os cálculos usam `Decimal` e os
pagamentos validam existência do boleto, saldo disponível e duplicidade.
O planejamento ordena os boletos por vencimento e não executa pagamentos.

Os valores exibidos nos widgets vêm das ferramentas. `ToolCallItem` e
`ToolCallOutputItem` associam cada resultado à sua chamada, sem interpretar texto
livre para descobrir qual operação foi executada. Pydantic valida os dados usados
na apresentação de saldo e boletos.

## Widgets e transmissão de eventos

Os arquivos em `test-ui/widgets/` definem os cartões de saldo, boletos, aprovação
e resultado. `WidgetTemplate` preenche esses modelos e `stream_widget` envia os
eventos da interface. A lista usa template Jinja; totais e formatação monetária
são preparados pelo backend.

O servidor usa `Runner.run` e renderiza a resposta estruturada após a execução.
O protocolo ChatKit usa SSE, mas o texto do LLM não é transmitido token a token.
O adaptador `stream_agent_response` transmite texto bruto; seu uso direto neste
contrato mostraria o JSON de `RespostaAgente` na conversa.

## Sessões e persistência

| Estado | Local | Duração |
| --- | --- | --- |
| Token e identidade da sessão anônima | Navegador e registro do backend | Até expirar ou reiniciar |
| Saldo e pagamentos simulados | Sessão web no backend | Em memória |
| Histórico do agente | `SQLiteSession` por conversa | Em memória no servidor web |
| Conversas e widgets | `StoreMemoria` | Em memória |
| Aprovação pendente | `ConversaFinanceira` | Até a decisão ou reinício |

Cada sessão tem finanças próprias; o Store verifica o proprietário de conversas
e itens. Atualizar a página cria outra sessão. Reiniciar o backend perde o estado
web, inclusive aprovações pendentes. A aplicação opera com uma instância e um worker.

Na CLI, o histórico SQLite é salvo em arquivo, mas as finanças continuam em memória.
Os detalhes de execução e limites estão no [guia de configuração](../deploy/README.md).

## Tracing e avaliações

O tracing nativo do SDK acompanha as execuções. O servidor web usa
`trace_include_sensitive_data=False` no `RunConfig`.

A validação combina testes determinísticos das regras e do protocolo com evals
usando o modelo real. Os cenários verificam seleção de ferramentas, pedidos de
esclarecimento, interrupção e rejeição HITL, isolamento e widgets.

Answer Quality verifica critérios objetivos da resposta. LLM-as-a-Judge usa um
agente avaliador com `output_type=ResultadoAvaliacao`, validado por Pydantic.
O avaliador participa apenas dos testes, não do atendimento ao usuário.

Os comandos estão na [seção Testes do README](../README.md#testes).
O [roteiro de demonstração](demonstracao.md) orienta a validação manual do pagamento.

## Segurança e limites da PoC

A chave OpenAI fica somente no backend. O frontend recebe a URL da API e o
`domainKey` público pelo endpoint de configuração.

O acesso é anônimo. O token separa sessões, mas não identifica uma pessoa.
CORS e domainKey não substituem autenticação. Limites de requisição, locks e
validação de proprietário são controles da aplicação.

A simulação não inclui persistência financeira durável, transações bancárias ou
recuperação distribuída de aprovações. Bloquear um pagamento duplicado em memória
não equivale a garantir idempotência em um sistema bancário.

## Referências

- [Material de estudo sobre os conceitos e experimentos](estudo_revisado.md).
- [Configuração e publicação na AWS](../deploy/aws/README.md).
