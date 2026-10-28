"""Dependências locais do Runner; não são enviadas ao modelo."""
from dataclasses import dataclass, field

from financeiro import EstadoFinanceiro, criar_estado_financeiro


@dataclass
class ContextoFinanceiro:
    quantidade_buscas: int = 0
    limite_buscas: int = 2
    estado: EstadoFinanceiro = field(default_factory=criar_estado_financeiro)


class LimiteBuscasExcedido(Exception):
    pass
