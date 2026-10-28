
import ast
import json
import sys

from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from agents import Runner, SQLiteSession, RunConfig
from agents.items import ToolCallOutputItem
from chatkit.server import ChatKitServer, stream_widget
from chatkit.widgets import WidgetTemplate
from chatkit.types import (
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
    AssistantMessageContent,
    AssistantMessageItem,
    ThreadItemDoneEvent,
    ThreadItemReplacedEvent
)

from store_memoria import StoreMemoria


# ---------------------------------------------------------
# Importação do agente financeiro
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent / "assistente-organizacao-financeira"

sys.path.insert(0, str(BACKEND_DIR))

from configuracao import agent
from ContextoFinanceiro import ContextoFinanceiro
from financeiro import obter_boleto


# ---------------------------------------------------------
# Widgets
# ---------------------------------------------------------

WIDGET_SALDO = WidgetTemplate.from_file(
    BASE_DIR / "widgets" / "saldo.widget"
)

WIDGET_BOLETOS = WidgetTemplate.from_file(
    BASE_DIR / "widgets" / "boletos.widget"
)

WIDGET_APROVACAO = WidgetTemplate.from_file(
    BASE_DIR / "widgets" / "aprovacao.widget"
)

WIDGET_RESULTADO = WidgetTemplate.from_file(
    BASE_DIR / "widgets" / "resultado_pagamento.widget"
)

# ---------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------

def formatar_moeda(valor: Decimal) -> str:
    valor_formatado = f"{valor:,.2f}"
    return (
        "R$ "
        + valor_formatado
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


# ---------------------------------------------------------
# Servidor ChatKit
# ---------------------------------------------------------

class ServidorFinanceiro(ChatKitServer[dict]):

    def __init__(self, store):
        super().__init__(store=store)

        self.sessoes = {}
        self.contextos_financeiros = {}
        self.estados_pendentes = {}
        self.widgets_aprovacao = {}
        self.aprovacoes_ativas = {}

    def remover_thread(self, thread_id):
        sessao = self.sessoes.pop(thread_id, None)
        if sessao is not None:
            sessao.close()
        self.contextos_financeiros.pop(thread_id, None)
        self.estados_pendentes.pop(thread_id, None)
        self.widgets_aprovacao.pop(thread_id, None)
        self.aprovacoes_ativas.pop(thread_id, None)

    def remover_usuario(self, user_id):
        for tid, owner in list(self.store.proprietarios.items()):
            if owner == user_id:
                self.remover_thread(tid)
        self.store.remover_usuario(user_id)

    async def emitir_mensagem(self, thread, context, mensagem):
        yield ThreadItemDoneEvent(
            item=AssistantMessageItem(
                thread_id=thread.id,
                id=self.store.generate_item_id(
                    "message", thread, context
                ),
                created_at=datetime.now(),
                content=[
                    AssistantMessageContent(text=mensagem)
                ],
            )
        )

    def obter_boleto_aprovacao(self, interrupcao):
        """Consulta o boleto de uma chamada específica, sem decidir outras chamadas."""
        if interrupcao.name != "pagar_boleto":
            raise ValueError("Ferramenta não permitida para aprovação.")

        argumentos = interrupcao.arguments

        if isinstance(argumentos, str):
            argumentos = json.loads(argumentos)

        boleto_id = argumentos["boleto_id"]

        boleto = obter_boleto(boleto_id)

        if boleto is None:
            raise ValueError(f"Boleto não encontrado: {boleto_id}")

        return boleto

    async def emitir_aprovacao(self, thread, context, boleto, interrupcao):
        approval_id = uuid4().hex
        self.aprovacoes_ativas[thread.id] = {
            "approval_id": approval_id,
            "interrupcao": interrupcao,
            "boleto": boleto,
        }
        widget = WIDGET_APROVACAO.build({
            "approval_id": approval_id,
            "boleto_id": boleto["id"],
            "descricao": boleto["descricao"],
            "valor": formatar_moeda(Decimal(str(boleto["valor"]))),
            "vencimento": datetime.strptime(
                boleto["vencimento"], "%Y-%m-%d"
                ).strftime("%d/%m/%Y"),
        })

        async for evento in stream_widget(
            thread,
            widget,
            copy_text="Pagamento aguardando aprovação.",
            generate_id=lambda item_type: self.store.generate_item_id(
                item_type, thread, context
            ),
        ):
            if isinstance(evento, ThreadItemDoneEvent):
                self.widgets_aprovacao[thread.id] = evento.item

            yield evento

    # -----------------------------------------------------
    # Mensagens do usuário
    # -----------------------------------------------------

    async def respond(
        self,
        thread: ThreadMetadata,
        input_user_message: UserMessageItem | None,
        context: dict,
    ) -> AsyncIterator[ThreadStreamEvent]:

        if input_user_message is None:
            return

        mensagem = " ".join(
            parte.text
            for parte in input_user_message.content
            if parte.type == "input_text"
        )

        if not mensagem.strip():
            return

        # Não inicia outra execução enquanto houver
        # uma decisão de pagamento pendente.
        if thread.id in self.estados_pendentes:
            async for evento in self.emitir_mensagem(
                thread,
                context,
                "Existe um pagamento aguardando sua decisão. "
                "Use os botões Aprovar ou Rejeitar.",
            ):
                yield evento
            return

        # Sessão por conversa
        if thread.id not in self.sessoes:
            self.sessoes[thread.id] = SQLiteSession(thread.id)

        sessao = self.sessoes[thread.id]

        # O limite de buscas vale por solicitação, não por toda a conversa.
        self.contextos_financeiros[thread.id] = ContextoFinanceiro()

        contexto_financeiro = self.contextos_financeiros[thread.id]

        # Execução do agente
        resultado = await Runner.run(
            agent,
            input=mensagem,
            session=sessao,
            context=contexto_financeiro,
            run_config=RunConfig(trace_include_sensitive_data=False),
        )

        # HITL: execução interrompida
        if resultado.interruptions:
            state = resultado.to_state()
            interrupcao = resultado.interruptions[0]
            boleto = self.obter_boleto_aprovacao(interrupcao)

            self.estados_pendentes[thread.id] = state

            async for evento in self.emitir_aprovacao(
                thread, context, boleto, interrupcao
            ):
                yield evento

            return


        # Resposta final
        resposta = resultado.final_output

        if resposta is None:
            async for evento in self.emitir_mensagem(
                thread,
                context,
                "Não foi possível concluir a solicitação.",
            ):
                yield evento
            return

        # Extração dos boletos retornados pelas tools
        boletos = None

        for item in resultado.new_items:
            if not isinstance(item, ToolCallOutputItem):
                continue

            dados = item.output

            if isinstance(dados, str):
                try:
                    dados = ast.literal_eval(dados.strip())
                except (ValueError, SyntaxError):
                    continue

            if (
                isinstance(dados, list)
                and all(
                    isinstance(b, dict)
                    and {"id", "descricao", "valor", "vencimento"}.issubset(b)
                    for b in dados
                )
            ):
                boletos = dados
                break

        # Widget de saldo
        if (
            resposta.tipo == "resposta"
            and resposta.visualizacao == "saldo"
            and resposta.saldo is not None
        ):
            widget = WIDGET_SALDO.build({
                "saldo": formatar_moeda(resposta.saldo)
            })

            async for evento in stream_widget(
                thread,
                widget,
                copy_text=resposta.mensagem,
                generate_id=lambda item_type: self.store.generate_item_id(
                    item_type, thread, context
                ),
            ):
                yield evento

            return

        # Widget de boletos
        if (
            resposta.tipo == "resposta"
            and resposta.visualizacao == "lista_boletos"
            and boletos is not None
        ):
            # children = [
            #     {
            #         "type": "Title",
            #         "value": "Boletos pendentes",
            #     }
            # ]


            children = [
                {
                    "type": "Title",
                    "value": "Seus boletos pendentes",
                },
                {
                    "type": "Text",
                    "value": f"{len(boletos)} compromisso(s) encontrado(s)",
                },
                {
                    "type": "Divider",
                },
            ]

            total = Decimal("0.00")

            for indice, boleto in enumerate(boletos):
                valor = Decimal(str(boleto["valor"]))
                total += valor

                vencimento = datetime.strptime(
                    boleto["vencimento"], "%Y-%m-%d"
                ).strftime("%d/%m/%Y")

                children.extend([
                    {
                        "type": "Row",
                        "children": [
                            {
                                "type": "Col",
                                "children": [
                                    {
                                        "type": "Text",
                                        "value": boleto["descricao"],
                                    },
                                    {
                                        "type": "Caption",
                                        "value": f"Vencimento: {vencimento}",
                                    },
                                ],
                            },
                            {
                                "type": "Title",
                                "value": formatar_moeda(valor),
                            },
                        ],
                    },
                ])

                if indice < len(boletos) - 1:
                    children.append({"type": "Divider"})

            children.extend([
                {"type": "Divider"},
                {
                    "type": "Row",
                    "children": [
                        {
                            "type": "Text",
                            "value": "Total pendente",
                        },
                        {
                            "type": "Title",
                            "value": formatar_moeda(total),
                        },
                    ],
                },
            ])


            # for boleto in boletos:
            #     children.append({
            #         "type": "Text",
            #         "value": (
            #             f"{boleto['descricao']} — "
            #             f"{formatar_moeda(Decimal(str(boleto['valor'])))} "
            #             f"— Vencimento: {boleto['vencimento']}"
            #         ),
            #     })

            widget = WIDGET_BOLETOS.build({
                "children": json.dumps(
                    children, ensure_ascii=False
                )
            })

            async for evento in stream_widget(
                thread,
                widget,
                copy_text=resposta.mensagem,
                generate_id=lambda item_type: self.store.generate_item_id(
                    item_type, thread, context
                ),
            ):
                yield evento

            return

        # Resposta textual
        async for evento in self.emitir_mensagem(
            thread, context, resposta.mensagem
        ):
            yield evento

    # -----------------------------------------------------
    # Ações dos botões do ChatKit
    # -----------------------------------------------------

    async def action(self, thread, action, sender, context):
        if action.type not in ("aprovar_pagamento", "rejeitar_pagamento"):
            return

        state = self.estados_pendentes.get(thread.id)
        ativa = self.aprovacoes_ativas.get(thread.id)
        if state is None or ativa is None:
            async for evento in self.emitir_mensagem(
                thread, context, "Não existe uma aprovação pendente para esta conversa."
            ):
                yield evento
            return

        payload = action.payload if isinstance(action.payload, dict) else {}
        widget_original = self.widgets_aprovacao.get(thread.id)
        if (payload.get("approval_id") != ativa["approval_id"]
                or (sender is not None and (widget_original is None or sender.id != widget_original.id))):
            async for evento in self.emitir_mensagem(
                thread, context,
                "Esta aprovação não está mais ativa. Use os botões do pagamento atual."
            ):
                yield evento
            return

        # O clique decide somente a operação exibida, nunca todas as interrupções.
        interrupcao = ativa["interrupcao"]
        boleto = ativa["boleto"]
        if action.type == "aprovar_pagamento":
            state.approve(interrupcao)
        else:
            state.reject(interrupcao, rejection_message="Pagamento rejeitado pelo usuário.")

        # Consumir antes de retomar impede o reenvio, inclusive após falha na execução.
        self.estados_pendentes.pop(thread.id, None)
        self.aprovacoes_ativas.pop(thread.id, None)
        self.widgets_aprovacao.pop(thread.id, None)

        resultado = await Runner.run(
            agent, state,
            context=self.contextos_financeiros[thread.id],
            session=self.sessoes[thread.id],
            run_config=RunConfig(trace_include_sensitive_data=False),
        )

        # Substituir o widget anterior antes de apresentar a próxima operação.
        if widget_original is not None:
            titulo = "Pagamento rejeitado" if action.type == "rejeitar_pagamento" else "Pagamento processado"
            if action.type == "aprovar_pagamento":
                for item in resultado.new_items:
                    if not isinstance(item, ToolCallOutputItem):
                        continue
                    dados = item.output
                    if isinstance(dados, str):
                        try:
                            dados = ast.literal_eval(dados)
                        except (ValueError, SyntaxError):
                            continue
                    if isinstance(dados, dict) and dados.get("status") == "ERRO":
                        titulo = "Pagamento não realizado"
            widget_original.widget = WIDGET_RESULTADO.build({
                "titulo": titulo,
                "boleto_id": boleto["id"],
                "descricao": boleto["descricao"],
                "valor": formatar_moeda(Decimal(str(boleto["valor"]))),
                "vencimento": datetime.strptime(boleto["vencimento"], "%Y-%m-%d").strftime("%d/%m/%Y"),
            })
            widget_original.copy_text = titulo
            yield ThreadItemReplacedEvent(item=widget_original)

        # O SDK conserva as chamadas ainda sem decisão. Exibir uma por vez.
        if resultado.interruptions:
            self.estados_pendentes[thread.id] = resultado.to_state()
            proxima = resultado.interruptions[0]
            boleto = self.obter_boleto_aprovacao(proxima)
            async for evento in self.emitir_aprovacao(thread, context, boleto, proxima):
                yield evento
            return

        resposta = resultado.final_output
        mensagem = resposta.mensagem if resposta is not None else "A solicitação foi processada, mas não houve resposta final."
        async for evento in self.emitir_mensagem(thread, context, mensagem):
            yield evento


# ---------------------------------------------------------
# Inicialização
# ---------------------------------------------------------

store = StoreMemoria()
servidor = ServidorFinanceiro(store=store)
