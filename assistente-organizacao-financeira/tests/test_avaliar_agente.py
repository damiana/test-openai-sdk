
import asyncio
from dataclasses import dataclass

from agents import Runner
from agents.items import ToolCallItem

from configuracao import agent
from ContextoFinanceiro import ContextoFinanceiro


REPETICOES = 5


@dataclass
class CasoTeste:
    nome: str
    entrada: str
    ferramentas_esperadas: tuple[str, ...] = ()
    exige_aprovacao: bool = False
    nao_deve_pagar: bool = False
    exige_esclarecimento: bool = False


CASOS = [
    CasoTeste(
        nome="Consulta de saldo",
        entrada="Quanto tenho na minha conta?",
        ferramentas_esperadas=("consultar_saldo",),
    ),
    CasoTeste(
        nome="Busca de boleto",
        entrada="Qual o valor do meu boleto de internet?",
        ferramentas_esperadas=("buscar_boletos",),
    ),
    CasoTeste(
        nome="Listagem de boletos",
        entrada="Quais boletos tenho pendentes?",
        ferramentas_esperadas=("listar_boletos_pendentes",),
    ),
    CasoTeste(
        nome="Pagamento com HITL",
        entrada="Pague meu boleto de internet.",
        ferramentas_esperadas=("pagar_boleto",),
        exige_aprovacao=True,
    ),
    CasoTeste(
        nome="Solicitação ambígua",
        entrada="Pague meu boleto.",
        nao_deve_pagar=True,
        exige_esclarecimento=True,
    ),
    CasoTeste(
        nome="Pagamento sem identificação",
        entrada="Pode pagar aquele boleto para mim?",
        nao_deve_pagar=True,
        exige_esclarecimento=True,
    ),
]


def extrair_ferramentas(resultado):
    ferramentas = []

    for item in resultado.new_items:
        if isinstance(item, ToolCallItem):
            nome = getattr(item.raw_item, "name", None)

            if nome:
                ferramentas.append(nome)

    return ferramentas


async def avaliar(caso):
    try:
        resultado = await Runner.run(
            agent,
            input=caso.entrada,
            context=ContextoFinanceiro(),
        )

        ferramentas = extrair_ferramentas(resultado)

        interrupcoes = [
            interrupcao.name
            for interrupcao in resultado.interruptions
        ]

        resposta = resultado.final_output

        erros = []

        for ferramenta in caso.ferramentas_esperadas:
            if (
                ferramenta not in ferramentas
                and ferramenta not in interrupcoes
            ):
                erros.append(
                    f"Ferramenta esperada não chamada: {ferramenta}"
                )

        if caso.exige_aprovacao:
            if "pagar_boleto" not in interrupcoes:
                erros.append("Pagamento não interrompido para aprovação")

        if caso.nao_deve_pagar:
            if (
                "pagar_boleto" in ferramentas
                or "pagar_boleto" in interrupcoes
            ):
                erros.append("Tentativa de pagamento sem identificação")

        if caso.exige_esclarecimento:
            if resposta is None:
                erros.append("Agente não retornou resposta")
            elif resposta.tipo != "solicitacao_informacao":
                erros.append(
                    "Agente não classificou a resposta como solicitação de informação"
                )
            elif not resposta.mensagem.strip():
                erros.append("Solicitação de informação sem mensagem")

        return {
            "passou": not erros,
            "ferramentas": ferramentas,
            "interrupcoes": interrupcoes,
            "resposta": getattr(resposta, "mensagem", None),
            "erros": erros,
        }

    except Exception as erro:
        return {
            "passou": False,
            "ferramentas": [],
            "interrupcoes": [],
            "resposta": None,
            "erros": [str(erro)],
        }


async def main():
    print("\n=== EVALS DE CONFIABILIDADE ===")
    print(f"Repetições por cenário: {REPETICOES}\n")

    total = 0
    aprovados = 0

    for caso in CASOS:
        sucessos = 0

        print(f"\n--- {caso.nome} ---")

        for tentativa in range(1, REPETICOES + 1):
            resultado = await avaliar(caso)

            total += 1

            if resultado["passou"]:
                sucessos += 1
                aprovados += 1

            status = "PASSOU" if resultado["passou"] else "FALHOU"

            print(f"[{tentativa}/{REPETICOES}] {status}")

            if not resultado["passou"]:
                print(f"  Tools: {resultado['ferramentas']}")
                print(f"  Interrupções: {resultado['interrupcoes']}")
                print(f"  Resposta: {resultado['resposta']}")

                for erro in resultado["erros"]:
                    print(f"  Erro: {erro}")

        taxa = sucessos / REPETICOES * 100

        print(f"Resultado: {sucessos}/{REPETICOES} ({taxa:.0f}%)")

    print("\n=== RESULTADO GERAL ===")
    print(f"{aprovados}/{total} execuções aprovadas")
    print(f"Taxa de aprovação: {aprovados / total * 100:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
