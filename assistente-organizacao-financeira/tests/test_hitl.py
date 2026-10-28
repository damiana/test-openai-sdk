
import asyncio
from decimal import Decimal

from agents import Runner

from configuracao import agent
from ContextoFinanceiro import ContextoFinanceiro
from financeiro import estado_financeiro


SALDO_INICIAL = Decimal("350.00")
BOLETO_ID = "BOL-002"
VALOR_BOLETO = Decimal("149.90")


def restaurar_estado():
    estado_financeiro["saldo"] = SALDO_INICIAL
    estado_financeiro["pagamentos_realizados"] = set()


async def iniciar_pagamento():
    resultado = await Runner.run(
        agent,
        input="Pague meu boleto de internet.",
        context=ContextoFinanceiro(estado=estado_financeiro),
    )

    assert len(resultado.interruptions) == 1, (
        "Esperada exatamente uma aprovação pendente"
    )

    interrupcao = resultado.interruptions[0]

    assert interrupcao.name == "pagar_boleto", (
        "A interrupção não corresponde à ferramenta de pagamento"
    )

    assert estado_financeiro["saldo"] == SALDO_INICIAL, (
        "Saldo alterado antes da aprovação"
    )

    assert not estado_financeiro["pagamentos_realizados"], (
        "Pagamento registrado antes da aprovação"
    )

    return resultado.to_state()


async def testar_rejeicao():
    restaurar_estado()

    state = await iniciar_pagamento()
    interrupcao = state.get_interruptions()[0]

    state.reject(
        interrupcao,
        rejection_message="Pagamento rejeitado pelo usuário.",
    )

    resultado = await Runner.run(
        agent,
        state,
        context=ContextoFinanceiro(estado=estado_financeiro),
    )

    assert not resultado.interruptions, (
        "Nova aprovação inesperada após rejeição"
    )

    assert estado_financeiro["saldo"] == SALDO_INICIAL, (
        "Saldo alterado após rejeição"
    )

    assert not estado_financeiro["pagamentos_realizados"], (
        "Pagamento registrado após rejeição"
    )


async def testar_aprovacao():
    restaurar_estado()

    state = await iniciar_pagamento()
    interrupcao = state.get_interruptions()[0]

    resposta = input("Autorizar o pagamento simulado de internet? (s/n): ").strip().lower()
    if resposta != "s":
        state.reject(interrupcao)
        await Runner.run(agent, state, context=ContextoFinanceiro(estado=estado_financeiro))
        raise AssertionError("Cenário de aprovação não autorizado pelo usuário.")
    state.approve(interrupcao)

    resultado = await Runner.run(
        agent,
        state,
        context=ContextoFinanceiro(estado=estado_financeiro),
    )

    assert not resultado.interruptions, (
        "Nova aprovação inesperada após aprovação"
    )

    assert estado_financeiro["saldo"] == (
        SALDO_INICIAL - VALOR_BOLETO
    ), "Saldo incorreto após pagamento"

    assert BOLETO_ID in estado_financeiro["pagamentos_realizados"], (
        "Pagamento não registrado"
    )

    assert len(estado_financeiro["pagamentos_realizados"]) == 1, (
        "Quantidade incorreta de pagamentos"
    )


async def main(incluir_aprovacao_manual=False):
    print("\n=== TESTES AUTOMATIZADOS DE HITL ===\n")

    testes = [
        ("Rejeição não altera saldo", testar_rejeicao),
    ]

    if incluir_aprovacao_manual:
        testes.append(("Aprovação humana executa pagamento", testar_aprovacao))

    aprovados = 0

    try:
        for nome, teste in testes:
            try:
                await teste()
                print(f"[PASSOU] {nome}")
                aprovados += 1
            except Exception as erro:
                print(f"[FALHOU] {nome}: {type(erro).__name__}: {erro}")
            finally:
                restaurar_estado()

        print(f"\n=== RESULTADO: {aprovados}/{len(testes)} ===")
    finally:
        restaurar_estado()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--aprovacao-manual", action="store_true")
    asyncio.run(main(parser.parse_args().aprovacao_manual))
