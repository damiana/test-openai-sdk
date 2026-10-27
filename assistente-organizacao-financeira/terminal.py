"""Interação pelo terminal, sessão SQLite e tracing por solicitação."""

from uuid import uuid4

from agents import Runner, SQLiteSession, MaxTurnsExceeded, trace
from agents.exceptions import UserError

from configuracao import agent
from ContextoFinanceiro import ContextoFinanceiro, LimiteBuscasExcedido
from hitl import resolver_aprovacoes


def main():

    session = SQLiteSession(
        f"teste-{uuid4()}",
        "conversas_financeiras.db"
    )

    try:
        print("\n=== ASSISTENTE FINANCEIRO ===")
        print("Digite 'sair' para encerrar.\n")

        while True:
            pergunta = input("\nVocê: ").strip()

            if pergunta.lower() == "sair":
                print("Encerrando...")
                break

            if not pergunta:
                continue

            contexto = ContextoFinanceiro()

            # Cria um trace para cada interação do usuário
            with trace("Assistente Financeiro - Interação"):

                # 1. Executa o agente
                result = Runner.run_sync(
                    agent,
                    pergunta,
                    context=contexto,
                    session=session,
                    max_turns=5
                )

                result = resolver_aprovacoes(agent, result, contexto, session)

                # 4. Exibe a resposta final
                print(f"\nAgente: {result.final_output}")

    except UserError as erro:
        if isinstance(erro.__cause__, LimiteBuscasExcedido):
            print("[ERRO] Limite de buscas atingido.")
        else:
            raise

    except MaxTurnsExceeded:
        print("[ERRO] Limite de turnos atingido.")


