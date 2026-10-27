
from typing import Literal
from pydantic import BaseModel


class RespostaAgente(BaseModel):
    tipo: Literal["resposta", "solicitacao_informacao"]
    mensagem: str
    campo_pendente: str | None = None
