"""Aprovação humana e retomada das execuções interrompidas."""

from agents import Runner


def resolver_aprovacoes(agent, result, contexto, session):
    while result.interruptions:
        print("\n--- APROVAÇÃO HUMANA (HITL) ---")

        state = result.to_state()

        for interruption in result.interruptions:
            print(f"Ferramenta: {interruption.name}")
            print(f"Argumentos: {interruption.arguments}")

            resposta = input(
                "Autorizar pagamento? (s/n): "
            ).strip().lower()

            if resposta == "s":
                state.approve(interruption)
                print("[HITL] Aprovado")
            else:
                state.reject(interruption)
                print("[HITL] Rejeitado")

        # 3. Retoma o agente após aprovação ou rejeição
        result = Runner.run_sync(
            agent,
            state,
            context=contexto,
            session=session,
            max_turns=5
        )

    return result
