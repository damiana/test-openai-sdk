"""Entrada pelo terminal e compatibilidade dos imports públicos da PoC."""

from configuracao import agent
from ContextoFinanceiro import ContextoFinanceiro, LimiteBuscasExcedido
from financeiro import (
    estado_financeiro, planejar_pagamentos, obter_saldo, obter_boletos,
    executar_pagamento_simulado,
)
from ferramentas import (
    consultar_saldo, consultar_limite_cartao, consultar_boleto, listar_boletos,
    buscar_boletos, gerar_plano_pagamentos, listar_boletos_pendentes, pagar_boleto,
)
from terminal import main


if __name__ == "__main__":
    main()
