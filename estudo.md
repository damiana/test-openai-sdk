## PoC:

Assistente de organização financeira

O agente consulta saldo, boletos e vencimentos, ajuda o cliente a priorizar pagamentos e executa operações simuladas mediante aprovação.

Permite explorar planejamento, memória, multiturn, Evals, HITL e interfaces interativas.

## 1. Onde estaria a profundidade técnica?

| Capacidade        | Desafio que a PoC demonstraria                |
| ----------------- | --------------------------------------------- |
| Agents SDK        | Orquestração do fluxo de atendimento          |
| Tools             | Consulta de informações e execução simulada   |
| Sessions          | Contexto entre múltiplas mensagens            |
| Memória           | Preferências e restrições do usuário          |
| Human-in-the-loop | Aprovação e rejeição de pagamentos            |
| Tracing           | Rastreabilidade de decisões e ferramentas     |
| Evals             | Qualidade, segurança e consistência do agente |
| Interface visual  | Apresentação e confirmação estruturada        |

E acrescentaria um experimento especialmente interessante: comparar o comportamento do agente com e sem memória, ou com diferentes instruções, usando o mesmo conjunto de Evals.

Isso transformaria a PoC em uma investigação técnica, não apenas uma demonstração funcional.

Você poderia apresentar resultados como taxa de seleção correta de ferramentas, preservação de contexto, tentativas de execução sem aprovação e conclusão das tarefas. Sem inventar métricas: os números viriam das execuções reais.

--

nomes, descrições, parâmetros e instruções precisam ser coerentes.

--

O que aprendemos?
Agora temos três responsabilidades separadas:
- LLM: decide qual descrição pesquisar.
- Runner: fornece o contexto à ferramenta.
- ContextoFinanceiro: mantém o contador das buscas.

--
Trade-off em previsibilidade versus flexibilidade, uma decisão importante na arquitetura de sistemas com agentes.

O LLM interpreta intenções. A aplicação garante invariantes.

Na nossa arquitetura:
- O agente decide qual boleto procurar.
- A ferramenta executa a busca.
- O backend controla quantas buscas são permitidas.
- A aplicação determina o que acontece quando o limite é atingido.

--

No OpenAI Agents SDK, podemos usar needs_approval=True na definição da ferramenta:
```python
@function_tool(needs_approval=True)
def pagar_boleto(boleto_id: str) -> dict:
    """Executa um pagamento simulado após aprovação humana."""
    return executar_pagamento_simulado(boleto_id)
````

```text
Tipo: tool_call_output_item
Resultado: Tool execution was not approved.
````

Isso mostra que o SDK bloqueou a execução da ferramenta, mas permitiu que o agente continuasse a conversa e explicasse o resultado.

--

Trace
https://platform.openai.com/logs?api=traces

1. Primeira imagem — Consulta de boletos
O trace apresenta:
- Assistente Organização Financeiro: execução do agente.
- turn: ciclo de processamento.
- POST /v1/responses: chamada ao modelo.
- listar_boletos_pendentes: execução da ferramenta.
O tempo total foi de aproximadamente 4,46 segundos, enquanto a ferramenta registrou menos de 1 ms. Isso sugere que, nessa interação, a maior parte do tempo foi consumida nas chamadas ao modelo.


2. Segunda imagem — Pagamento
Aqui temos algo mais interessante: aparecem dois spans de pagar_boleto, distribuídos em dois grupos task.
Isso merece investigação. Pode estar relacionado à interrupção e à retomada do HITL, mas não devemos concluir que houve dois pagamentos apenas pela quantidade de spans.
O que sabemos é que o SDK registrou duas ocorrências relacionadas à ferramenta. Para confirmar se houve uma ou duas execuções efetivas, precisamos abrir cada span e examinar seus argumentos, resultados e eventuais registros de aprovação.

--

O que aprendemos com os Evals?
Agora experimentamos três níveis de avaliação:
1. Comportamental: o agente escolheu a ferramenta correta?
2. Determinístico: as regras financeiras e de segurança foram respeitadas?
3. Semântico: a resposta representa corretamente os dados e comunica o resultado de maneira adequada?

--
