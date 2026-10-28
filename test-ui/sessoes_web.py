"""Sessões anônimas e efêmeras para a demonstração de uma única instância."""
import asyncio
from collections import deque
from dataclasses import dataclass, field
import secrets
import time
from uuid import uuid4

from fastapi import HTTPException
from financeiro import criar_estado_financeiro


@dataclass
class SessaoWeb:
    user_id: str = field(default_factory=lambda: uuid4().hex)
    estado: dict = field(default_factory=criar_estado_financeiro)
    criada_em: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    requisicoes: deque = field(default_factory=deque)
    total_requisicoes: int = 0


class SessoesWeb:
    def __init__(self, ao_expirar, ttl=7200, max_sessoes=50):
        self.sessoes = {}
        self.ao_expirar = ao_expirar
        self.ttl = ttl
        self.max_sessoes = max_sessoes
        self.criacoes = deque()

    def limpar_expiradas(self):
        agora = time.monotonic()
        for token, sessao in list(self.sessoes.items()):
            if agora - sessao.criada_em >= self.ttl and not sessao.lock.locked():
                self.ao_expirar(sessao.user_id)
                del self.sessoes[token]

    def criar(self):
        self.limpar_expiradas()
        agora = time.monotonic()
        while self.criacoes and self.criacoes[0] <= agora - 60:
            self.criacoes.popleft()
        if len(self.sessoes) >= self.max_sessoes or len(self.criacoes) >= 20:
            raise HTTPException(429, "Limite de sessões da demonstração atingido. Tente mais tarde.")
        token = secrets.token_urlsafe(32)
        self.sessoes[token] = SessaoWeb()
        self.criacoes.append(agora)
        return token

    def obter(self, authorization):
        self.limpar_expiradas()
        token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        sessao = self.sessoes.get(token)
        if sessao is None or time.monotonic() - sessao.criada_em >= self.ttl:
            raise HTTPException(401, "Sessão encerrada ou servidor reiniciado. Inicie uma nova demonstração.")
        return sessao

    @staticmethod
    def limitar(sessao):
        agora = time.monotonic()
        while sessao.requisicoes and sessao.requisicoes[0] <= agora - 60:
            sessao.requisicoes.popleft()
        if len(sessao.requisicoes) >= 60 or sessao.total_requisicoes >= 300:
            raise HTTPException(429, "Limite de solicitações desta sessão atingido.")
        sessao.requisicoes.append(agora)
        sessao.total_requisicoes += 1
