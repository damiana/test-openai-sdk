"""Ferramentas disponibilizadas ao agente pelo OpenAI Agents SDK."""

from agents import RunContextWrapper, function_tool
from ContextoFinanceiro import ContextoFinanceiro, LimiteBuscasExcedido
from financeiro import (
    obter_saldo, obter_boletos, planejar_pagamentos, executar_pagamento_simulado,
)


@function_tool
def consultar_saldo() -> float:
    """Consulta o saldo disponível da conta bancária."""
    print("[TOOL] Executando consultar_saldo()")
    return obter_saldo()


@function_tool
def consultar_limite_cartao() -> float:
    """Consulta o limite disponível do cartão de crédito."""
    print("[TOOL] Executando consultar_limite_cartao()")
    return 5000.00


@function_tool
def consultar_boleto(boleto_id: str) -> dict:
    """Consulta os detalhes de um boleto pelo seu identificador."""

    boletos = {
        "BOL-001": {"descricao": "Energia elétrica", "valor": 280.00},
        "BOL-002": {"descricao": "Internet", "valor": 149.90},
        "BOL-003": {"descricao": "Água", "valor": 92.50},
    }

    print(f"[TOOL] Consultando boleto: {boleto_id}")

    return boletos.get(
        boleto_id,
        {"erro": "Boleto não encontrado"}
    )


@function_tool
def listar_boletos() -> list[dict]:
    """Lista os boletos disponíveis do cliente, incluindo seus identificadores, descrições e valores."""

    print("[TOOL] Executando listar_boletos()")

    return [
        {
            "id": "BOL-001",
            "descricao": "Energia elétrica",
            "valor": 280.00
        },
        {
            "id": "BOL-002",
            "descricao": "Internet",
            "valor": 149.90
        },
        {
            "id": "BOL-003",
            "descricao": "Água",
            "valor": 92.50
        }
    ]


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
    
    boletos = obter_boletos()

    return [
        boleto
        for boleto in boletos
        if descricao.casefold() in boleto["descricao"].casefold()
    ]


@function_tool
def gerar_plano_pagamentos() -> dict:
    """Gera um plano de pagamento dos boletos pendentes,
    considerando o saldo disponível e a ordem de vencimento.
    Não realiza pagamentos.
    """

    print("[TOOL] Gerando plano de pagamentos")

    return planejar_pagamentos(
        saldo=obter_saldo(),
        boletos=obter_boletos()
    )


@function_tool
def listar_boletos_pendentes() -> list[dict]:
    """Lista os boletos pendentes com valores e vencimentos."""
    return obter_boletos()


@function_tool(needs_approval=True)
def pagar_boleto(boleto_id: str) -> dict:
    """Executa um pagamento simulado após aprovação humana."""
    print(f"[TOOL] Executando pagamento: {boleto_id}")
    return executar_pagamento_simulado(boleto_id)


