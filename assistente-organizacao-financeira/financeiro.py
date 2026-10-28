"""Estado e regras financeiras simuladas, independentes do SDK."""

from decimal import Decimal


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


def obter_saldo() -> float:
    return float(estado_financeiro["saldo"])


def obter_boletos() -> list[dict]:
    boletos = [
        {"id": "BOL-001", "descricao": "Energia elétrica",
         "valor": 280.00, "vencimento": "2026-10-26"},
        {"id": "BOL-002", "descricao": "Internet",
         "valor": 149.90, "vencimento": "2026-10-28"},
        {"id": "BOL-003", "descricao": "Água",
         "valor": 92.50, "vencimento": "2026-10-27"}
    ]

    return [
        b for b in boletos
        if b["id"] not in estado_financeiro["pagamentos_realizados"]
    ]


estado_financeiro = {
    "saldo": Decimal("350.00"),
    "pagamentos_realizados": set()
}



def executar_pagamento_simulado(boleto_id: str) -> dict:
    if boleto_id in estado_financeiro["pagamentos_realizados"]:
        return {
            "status": "ERRO",
            "motivo": "Boleto já pago"
        }

    boletos = obter_boletos()

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
    saldo = Decimal(str(obter_saldo()))

    if valor > saldo:
        return {
            "status": "ERRO",
            "motivo": "Saldo insuficiente"
        }

    estado_financeiro["saldo"] -= valor
    estado_financeiro["pagamentos_realizados"].add(boleto_id)

    return {
        "status": "PAGO",
        "boleto_id": boleto_id,
        "valor": str(valor),
        "saldo_restante": str(estado_financeiro["saldo"])
    }



