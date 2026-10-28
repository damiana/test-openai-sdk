"""Estado e regras financeiras simuladas, independentes do SDK."""

from decimal import Decimal
from typing import TypedDict


class Boleto(TypedDict):
    id: str
    descricao: str
    valor: float
    vencimento: str


class EstadoFinanceiro(TypedDict):
    saldo: Decimal
    pagamentos_realizados: set[str]



def planejar_pagamentos(saldo: float, boletos: list[dict]) -> dict:
    saldo_disponivel = Decimal(str(saldo))
    saldo_restante = saldo_disponivel

    boletos_ordenados = sorted(
        boletos,
        key=lambda boleto: boleto["vencimento"]
    )

    selecionados = []
    nao_selecionados = []

    for boleto in boletos_ordenados:
        valor = Decimal(str(boleto["valor"]))

        if valor <= saldo_restante:
            selecionados.append(boleto)
            saldo_restante -= valor
        else:
            nao_selecionados.append(boleto)

    total = sum(
        (Decimal(str(b["valor"])) for b in boletos_ordenados),
        Decimal("0")
    )

    return {
        "boletos_selecionados": selecionados,
        "boletos_nao_selecionados": nao_selecionados,
        "total_pendente": str(total.quantize(Decimal("0.01"))),
        "saldo_suficiente": saldo_disponivel >= total,
        "saldo_restante": str(saldo_restante.quantize(Decimal("0.01")))
    }


def obter_saldo(estado: EstadoFinanceiro | None = None) -> float:
    return float((estado if estado is not None else estado_financeiro)["saldo"])


def _boletos_simulados() -> list[Boleto]:
    return [
        {"id": "BOL-001", "descricao": "Energia elétrica",
         "valor": 280.00, "vencimento": "2026-10-26"},
        {"id": "BOL-002", "descricao": "Internet",
         "valor": 149.90, "vencimento": "2026-10-28"},
        {"id": "BOL-003", "descricao": "Água",
         "valor": 92.50, "vencimento": "2026-10-27"}
    ]


def obter_boleto(boleto_id: str) -> Boleto | None:
    """Metadados da simulação, inclusive após pagamento, para a interface HITL."""
    return next((b for b in _boletos_simulados() if b["id"] == boleto_id), None)


def obter_boletos(estado: EstadoFinanceiro | None = None) -> list[Boleto]:
    estado_atual = estado if estado is not None else estado_financeiro
    boletos = _boletos_simulados()
    return [
        b for b in boletos
        if b["id"] not in estado_atual["pagamentos_realizados"]
    ]


def criar_estado_financeiro() -> EstadoFinanceiro:
    """Cada sessão começa com os mesmos valores da simulação original."""
    return {"saldo": Decimal("350.00"), "pagamentos_realizados": set()}


# Compatibilidade com chamadas antigas e avaliações existentes.
estado_financeiro = criar_estado_financeiro()


def executar_pagamento_simulado(
    boleto_id: str, estado: EstadoFinanceiro | None = None
) -> dict:
    estado_atual = estado if estado is not None else estado_financeiro
    if boleto_id in estado_atual["pagamentos_realizados"]:
        return {
            "status": "ERRO",
            "motivo": "Boleto já pago"
        }

    boletos = obter_boletos(estado_atual)

    boleto = next(
        (b for b in boletos if b["id"] == boleto_id),
        None
    )

    if boleto is None:
        return {
            "status": "ERRO",
            "motivo": "Boleto inexistente"
        }

    valor = Decimal(str(boleto["valor"]))
    saldo = estado_atual["saldo"]

    if valor > saldo:
        return {
            "status": "ERRO",
            "motivo": "Saldo insuficiente"
        }

    estado_atual["saldo"] -= valor
    estado_atual["pagamentos_realizados"].add(boleto_id)

    return {
        "status": "PAGO",
        "boleto_id": boleto_id,
        "valor": str(valor),
        "saldo_restante": str(estado_atual["saldo"])
    }



