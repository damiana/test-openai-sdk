from dataclasses import dataclass

""" Annotation que facilita a criação de classes para armazenar dados.."""
@dataclass
class ContextoFinanceiro:
    quantidade_buscas: int = 0
    limite_buscas: int = 2

class LimiteBuscasExcedido(Exception):
    pass
