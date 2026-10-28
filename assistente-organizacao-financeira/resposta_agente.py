from typing import Literal
from pydantic import BaseModel, Field
from decimal import Decimal


class RespostaAgente(BaseModel):
    tipo: Literal["resposta", "solicitacao_informacao"]
    mensagem: str
    campo_pendente: str | None = None

    visualizacao: Literal[
        "texto",
        "saldo",
        "lista_boletos"
    ] = Field(default="texto")
    
    saldo: Decimal | None = None