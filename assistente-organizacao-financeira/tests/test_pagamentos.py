
from decimal import Decimal

from ferramentas import executar_pagamento_simulado
from financeiro import estado_financeiro

SALDO_INICIAL = Decimal("350.00")


def restaurar_estado():
    estado_financeiro["saldo"] = SALDO_INICIAL
    estado_financeiro["pagamentos_realizados"] = set()


def executar_teste(nome, teste):
    restaurar_estado()

    try:
        teste()
        print(f"[PASSOU] {nome}")
        return True
    except AssertionError as erro:
        print(f"[FALHOU] {nome}: {erro}")
        return False
    except Exception as erro:
        print(f"[ERRO] {nome}: {type(erro).__name__}: {erro}")
        return False
    finally:
        restaurar_estado()


def teste_boleto_inexistente():
    resultado = executar_pagamento_simulado("BOL-999")

    assert resultado["status"] == "ERRO"
    assert resultado["motivo"] == "Boleto inexistente"
    assert estado_financeiro["saldo"] == SALDO_INICIAL
    assert not estado_financeiro["pagamentos_realizados"]


def teste_saldo_insuficiente():
    estado_financeiro["saldo"] = Decimal("10.00")

    resultado = executar_pagamento_simulado("BOL-001")

    assert resultado["status"] == "ERRO"
    assert resultado["motivo"] == "Saldo insuficiente"
    assert estado_financeiro["saldo"] == Decimal("10.00")
    assert not estado_financeiro["pagamentos_realizados"]


def teste_pagamento_aprovado():
    resultado = executar_pagamento_simulado("BOL-002")

    assert resultado["status"] == "PAGO"
    assert resultado["boleto_id"] == "BOL-002"
    assert estado_financeiro["saldo"] == Decimal("200.10")
    assert "BOL-002" in estado_financeiro["pagamentos_realizados"]


def teste_pagamento_duplicado():
    primeiro = executar_pagamento_simulado("BOL-002")
    saldo_apos_primeiro = estado_financeiro["saldo"]

    segundo = executar_pagamento_simulado("BOL-002")

    assert primeiro["status"] == "PAGO"
    assert segundo["status"] == "ERRO"
    assert segundo["motivo"] == "Boleto já pago"
    assert estado_financeiro["saldo"] == saldo_apos_primeiro
    assert len(estado_financeiro["pagamentos_realizados"]) == 1


def main():
    print("\n=== TESTES DAS REGRAS FINANCEIRAS ===\n")

    testes = [
        ("Boleto inexistente", teste_boleto_inexistente),
        ("Saldo insuficiente", teste_saldo_insuficiente),
        ("Pagamento realizado", teste_pagamento_aprovado),
        ("Pagamento duplicado", teste_pagamento_duplicado),
    ]

    aprovados = sum(
        executar_teste(nome, teste)
        for nome, teste in testes
    )

    print(f"\n=== RESULTADO: {aprovados}/{len(testes)} ===")


if __name__ == "__main__":
    main()
