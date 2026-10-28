"""Ferramentas disponibilizadas ao agente pelo OpenAI Agents SDK."""

from agents import RunContextWrapper, function_tool
from ContextoFinanceiro import ContextoFinanceiro, LimiteBuscasExcedido
from financeiro import (
    obter_saldo, obter_boletos, obter_boleto, _boletos_simulados,
    planejar_pagamentos, executar_pagamento_simulado,
)


@function_tool
def consultar_saldo(ctx: RunContextWrapper[ContextoFinanceiro]) -> float:
    """Consulta o saldo disponível da conta bancária."""
    print("[TOOL] Executando consultar_saldo()")
    return obter_saldo(ctx.context.estado)


@function_tool
def consultar_limite_cartao() -> float:
    """Consulta o limite disponível do cartão de crédito."""
    print("[TOOL] Executando consultar_limite_cartao()")
    return 5000.00


@function_tool
def consultar_boleto(boleto_id: str) -> dict:
    """Consulta os detalhes de um boleto pelo seu identificador."""

    boleto = obter_boleto(boleto_id)
    if boleto is None:
        return {"erro": "Boleto não encontrado"}
    return {"descricao": boleto["descricao"], "valor": boleto["valor"]}


@function_tool
def listar_boletos() -> list[dict]:
    """Lista os boletos disponíveis do cliente, incluindo seus identificadores, descrições e valores."""
    return [{k: b[k] for k in ("id", "descricao", "valor")} for b in _boletos_simulados()]


@function_tool(failure_error_function=None) 
def buscar_boletos(
    ctx: RunContextWrapper[ContextoFinanceiro],
    descricao: str
) -> list[dict]:
    """Busca boletos pela descrição informada pelo usuário.

    Args:
        descricao: Texto usado para localizar boletos pela descrição.
    """

    if ctx.context.quantidade_buscas >= ctx.context.limite_buscas:
        print("[BLOQUEIO] Limite de buscas atingido")
        raise LimiteBuscasExcedido("Limite de buscas atingido")
    
    ctx.context.quantidade_buscas += 1

    print(f"[CONTEXTO] Total de buscas: {ctx.context.quantidade_buscas}")
    print(f"[TOOL] Buscando boletos por: {descricao}")
    
    boletos = obter_boletos(ctx.context.estado)

    return [
        boleto
        for boleto in boletos
        if descricao.casefold() in boleto["descricao"].casefold()
    ]


@function_tool
def gerar_plano_pagamentos(ctx: RunContextWrapper[ContextoFinanceiro]) -> dict:
    """Gera um plano de pagamento dos boletos pendentes,
    considerando o saldo disponível e a ordem de vencimento.
    Não realiza pagamentos.
    """

    print("[TOOL] Gerando plano de pagamentos")

    return planejar_pagamentos(
        saldo=obter_saldo(ctx.context.estado),
        boletos=obter_boletos(ctx.context.estado)
    )


@function_tool
def listar_boletos_pendentes(ctx: RunContextWrapper[ContextoFinanceiro]) -> list[dict]:
    """Lista os boletos pendentes com valores e vencimentos."""
    return obter_boletos(ctx.context.estado)


@function_tool(needs_approval=True)
def pagar_boleto(ctx: RunContextWrapper[ContextoFinanceiro], boleto_id: str) -> dict:
    """Executa um pagamento simulado após aprovação humana."""
    print(f"[TOOL] Executando pagamento: {boleto_id}")
    return executar_pagamento_simulado(boleto_id, ctx.context.estado)


