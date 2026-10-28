"""Adaptação do agente financeiro para mensagens, widgets e actions do ChatKit."""
import json
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from agents import Runner, RunConfig, RunState, SQLiteSession
from agents.items import ToolCallItem, ToolCallOutputItem
from chatkit.agents import simple_to_agent_input
from chatkit.server import ChatKitServer, stream_widget
from chatkit.types import (
    AssistantMessageContent, AssistantMessageItem, ThreadItemDoneEvent,
    ThreadItemReplacedEvent, ThreadMetadata, ThreadStreamEvent, UserMessageItem,
    WidgetItem,
)
from chatkit.widgets import WidgetTemplate
from pydantic import TypeAdapter

from store_memoria import StoreMemoria

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent / "assistente-organizacao-financeira"))
from configuracao import agent
from ContextoFinanceiro import ContextoFinanceiro
from financeiro import Boleto, obter_boleto

WIDGET_BOLETOS = WidgetTemplate.from_file(BASE_DIR / "widgets/boletos.widget")
WIDGET_SALDO = WidgetTemplate.from_file(BASE_DIR / "widgets/saldo.widget")
WIDGET_APROVACAO = WidgetTemplate.from_file(BASE_DIR / "widgets/aprovacao.widget")
WIDGET_RESULTADO = WidgetTemplate.from_file(BASE_DIR / "widgets/resultado_pagamento.widget")
BOLETOS = TypeAdapter(list[Boleto])
SALDO = TypeAdapter(Decimal)
RUN_CONFIG = RunConfig(trace_include_sensitive_data=False)


def formatar_moeda(valor: Decimal) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def dados_boleto(boleto):
    return {
        "boleto_id": boleto["id"], "descricao": boleto["descricao"],
        "valor": formatar_moeda(Decimal(str(boleto["valor"]))) if boleto["valor"] is not None else "Não disponível",
        "vencimento": datetime.strptime(boleto["vencimento"], "%Y-%m-%d").strftime("%d/%m/%Y")
        if boleto.get("vencimento") else "Não disponível",
    }


def resultado_ferramenta(resultado, nome, call_id=None):
    """Associa o output nativo à chamada que o produziu; não interpreta strings."""
    chamadas = {
        item.raw_item.call_id: item.raw_item.name
        for item in resultado.new_items if isinstance(item, ToolCallItem)
    }
    for item in reversed(resultado.new_items):
        if isinstance(item, ToolCallOutputItem) and (
            item.call_id == call_id if call_id is not None else chamadas.get(item.call_id) == nome
        ):
            return item.output
    return None


def widget_boletos(boletos):
    return WIDGET_BOLETOS.build({
        "boletos": [dados_boleto(boleto) for boleto in boletos],
        "total": formatar_moeda(sum((Decimal(str(b["valor"])) for b in boletos), Decimal("0.00"))),
    })


def titulo_pagamento(output, boleto_id):
    """A decisão humana autoriza; somente o resultado financeiro confirma sucesso."""
    if isinstance(output, dict):
        if output.get("status") == "PAGO" and output.get("boleto_id") == boleto_id:
            return "Pagamento realizado"
        if output.get("status") == "ERRO":
            return "Pagamento não realizado"
    return "Resultado não confirmado"


@dataclass
class ConversaFinanceira:
    sessao: SQLiteSession
    contexto: ContextoFinanceiro
    estado: RunState | None = None
    aprovacao: dict | None = None
    widget: WidgetItem | None = None


class ServidorFinanceiro(ChatKitServer[dict]):
    def __init__(self, store):
        super().__init__(store=store)
        self.conversas: dict[str, ConversaFinanceira] = {}

    def remover_thread(self, thread_id):
        conversa = self.conversas.pop(thread_id, None)
        if conversa is not None:
            conversa.sessao.close()

    def remover_usuario(self, user_id):
        for tid, owner in list(self.store.proprietarios.items()):
            if owner == user_id:
                self.remover_thread(tid)
        self.store.remover_usuario(user_id)

    async def emitir_mensagem(self, thread, context, mensagem):
        yield ThreadItemDoneEvent(item=AssistantMessageItem(
            thread_id=thread.id, id=self.store.generate_item_id("message", thread, context),
            created_at=datetime.now(), content=[AssistantMessageContent(text=mensagem)],
        ))

    async def emitir_widget(self, thread, context, widget, copy_text):
        async for evento in stream_widget(
            thread, widget, copy_text=copy_text,
            generate_id=lambda item_type: self.store.generate_item_id(item_type, thread, context),
        ):
            yield evento

    async def emitir_resultado(self, thread, context, resultado):
        """Mesmo tratamento na resposta inicial e na retomada do HITL."""
        conversa = self.conversas[thread.id]
        if resultado.interruptions:
            interrupcao = resultado.interruptions[0]
            if interrupcao.name != "pagar_boleto":
                raise ValueError("Ferramenta não permitida para aprovação.")
            argumentos = json.loads(interrupcao.arguments) if isinstance(interrupcao.arguments, str) else interrupcao.arguments
            boleto_id = argumentos["boleto_id"]
            # Um identificador inexistente também pode ser rejeitado com segurança.
            boleto = obter_boleto(boleto_id) or {
                "id": boleto_id, "descricao": "Boleto não encontrado", "valor": None, "vencimento": None,
            }
            approval_id = uuid4().hex
            conversa.estado = resultado.to_state()
            conversa.aprovacao = {"approval_id": approval_id, "interrupcao": interrupcao, "boleto": boleto}
            widget = WIDGET_APROVACAO.build({"approval_id": approval_id, **dados_boleto(boleto)})
            async for evento in self.emitir_widget(thread, context, widget, "Pagamento aguardando aprovação."):
                if isinstance(evento, ThreadItemDoneEvent):
                    conversa.widget = evento.item
                yield evento
            return

        resposta = resultado.final_output
        if resposta is None:
            mensagem = "Não foi possível concluir a solicitação."
        else:
            mensagem = resposta.mensagem
            saldo = resultado_ferramenta(resultado, "consultar_saldo")
            boletos = resultado_ferramenta(resultado, "listar_boletos_pendentes")
            if resposta.tipo == "resposta" and resposta.visualizacao == "saldo" and saldo is not None:
                widget = WIDGET_SALDO.build({"saldo": formatar_moeda(SALDO.validate_python(saldo))})
                async for evento in self.emitir_widget(thread, context, widget, mensagem):
                    yield evento
                return
            if resposta.tipo == "resposta" and resposta.visualizacao == "lista_boletos" and boletos is not None:
                widget = widget_boletos(BOLETOS.validate_python(boletos))
                async for evento in self.emitir_widget(thread, context, widget, mensagem):
                    yield evento
                return
        async for evento in self.emitir_mensagem(thread, context, mensagem):
            yield evento

    async def respond(
        self, thread: ThreadMetadata, input_user_message: UserMessageItem | None, context: dict,
    ) -> AsyncIterator[ThreadStreamEvent]:
        if input_user_message is None or not any(
            parte.type == "input_text" and parte.text.strip() for parte in input_user_message.content
        ):
            return
        conversa = self.conversas.get(thread.id)
        if conversa is not None and conversa.estado is not None:
            async for evento in self.emitir_mensagem(
                thread, context, "Existe um pagamento aguardando sua decisão. Use os botões Aprovar ou Rejeitar."
            ):
                yield evento
            return
        # Dependência explícita: nunca cair no estado global da CLI em uma requisição web.
        contexto = ContextoFinanceiro(estado=context["estado_financeiro"])
        if conversa is None:
            conversa = ConversaFinanceira(SQLiteSession(thread.id), contexto)
            self.conversas[thread.id] = conversa
        else:
            conversa.contexto = contexto
        # stream_agent_response transmite o texto bruto do modelo; com output_type
        # isso exporia o JSON. Preservamos a resposta validada antes de renderizar.
        resultado = await Runner.run(
            agent, input=await simple_to_agent_input(input_user_message),
            session=conversa.sessao, context=contexto, run_config=RUN_CONFIG,
        )
        async for evento in self.emitir_resultado(thread, context, resultado):
            yield evento

    async def action(self, thread, action, sender, context):
        if action.type not in ("aprovar_pagamento", "rejeitar_pagamento"):
            return
        conversa = self.conversas.get(thread.id)
        if conversa is None or conversa.estado is None or conversa.aprovacao is None:
            async for evento in self.emitir_mensagem(thread, context, "Não existe uma aprovação pendente para esta conversa."):
                yield evento
            return
        ativa, widget = conversa.aprovacao, conversa.widget
        payload = action.payload if isinstance(action.payload, dict) else {}
        if payload.get("approval_id") != ativa["approval_id"] or (
            sender is not None and (widget is None or sender.id != widget.id)
        ):
            async for evento in self.emitir_mensagem(thread, context, "Esta aprovação não está mais ativa. Use os botões do pagamento atual."):
                yield evento
            return
        state = conversa.estado
        interrupcao = ativa["interrupcao"]
        aprovado = action.type == "aprovar_pagamento"
        if aprovado:
            state.approve(interrupcao)
        else:
            state.reject(interrupcao, rejection_message="Pagamento rejeitado pelo usuário.")
        # Consumir antes de retomar impede reenvios, inclusive após falha.
        conversa.estado = conversa.aprovacao = conversa.widget = None
        try:
            resultado = await Runner.run(
                agent, state, context=conversa.contexto, session=conversa.sessao, run_config=RUN_CONFIG,
            )
        except Exception:
            if widget is not None:
                widget.widget = WIDGET_RESULTADO.build({"titulo": "Resultado não confirmado", **dados_boleto(ativa["boleto"])})
                widget.copy_text = "Resultado não confirmado. Consulte o saldo antes de tentar novamente."
                yield ThreadItemReplacedEvent(item=widget)
            raise
        if widget is not None:
            titulo = "Pagamento rejeitado"
            if aprovado:
                output = resultado_ferramenta(resultado, "pagar_boleto", interrupcao.raw_item.call_id)
                titulo = titulo_pagamento(output, ativa["boleto"]["id"])
            widget.widget = WIDGET_RESULTADO.build({"titulo": titulo, **dados_boleto(ativa["boleto"])})
            widget.copy_text = titulo
            yield ThreadItemReplacedEvent(item=widget)
        async for evento in self.emitir_resultado(thread, context, resultado):
            yield evento


store = StoreMemoria()
servidor = ServidorFinanceiro(store=store)
