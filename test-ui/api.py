"""API ChatKit com estado isolado por sessão e configuração para hospedagem HTTPS."""
from contextlib import asynccontextmanager
import json
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from chatkit.server import StreamingResult
from chatkit.store import NotFoundError
from agents import trace

# O servidor configura o caminho dos módulos financeiros compartilhados com a CLI.
from servidor_chatkit import servidor
from sessoes_web import SessoesWeb

origens = [value.strip() for value in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if value.strip()]


@asynccontextmanager
async def lifespan(app):
    if os.getenv("APP_ENV") == "production":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Configure OPENAI_API_KEY no backend.")
        if not origens or any(not origin.startswith("https://") or "*" in origin for origin in origens):
            raise RuntimeError("CORS_ORIGINS deve conter somente as origens HTTPS autorizadas.")
    yield


app = FastAPI(lifespan=lifespan)
sessoes = SessoesWeb(ao_expirar=servidor.remover_usuario)


@app.get("/health")
async def health():
    return {"status": "ok", "state": "ephemeral"}


@app.get("/config.js", include_in_schema=False)
async def configuracao_publica():
    # Lista explícita: nunca serializar o ambiente ou segredos do backend.
    config = {
        "chatkitApiURL": os.getenv("PUBLIC_CHATKIT_API_URL", "/chatkit"),
        "domainKey": os.getenv("CHATKIT_DOMAIN_KEY", "local-dev"),
    }
    content = "window.__FINAI_CONFIG__ = " + json.dumps(config) + ";\n"
    return Response(content, media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.post("/session")
async def criar_sessao():
    token = sessoes.criar()
    return Response(json.dumps({"token": token}), media_type="application/json", headers={"Cache-Control": "no-store"})


@app.post("/chatkit")
async def chatkit_endpoint(request: Request):
    sessao = sessoes.obter(request.headers.get("Authorization", ""))
    sessoes.limitar(sessao)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 262144:
            raise HTTPException(413, "Solicitação muito grande.")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "JSON inválido.") from None
    if not isinstance(payload, dict):
        raise HTTPException(400, "Solicitação inválida.")
    if sessao.lock.locked():
        raise HTTPException(409, "Aguarde a solicitação em andamento.")
    await sessao.lock.acquire()
    context = {"user_id": sessao.user_id, "estado_financeiro": sessao.estado,
               "on_delete_thread": servidor.remover_thread}
    try:
        thread_id = payload.get("params", {}).get("thread_id") if isinstance(payload.get("params", {}), dict) else None
        if thread_id:
            servidor.store.autorizar_thread(thread_id, context)
        resultado = await servidor.process(bytes(body), context)
        if isinstance(resultado, StreamingResult):
            async def eventos():
                try:
                    with trace("Assistente Financeiro - ChatKit"):
                        async for evento in resultado:
                            yield evento
                finally:
                    sessao.lock.release()
            return StreamingResponse(eventos(), media_type="text/event-stream", headers={
                "Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no",
            })
        sessao.lock.release()
        return Response(content=resultado.json, media_type="application/json", headers={"Cache-Control": "no-store"})
    except NotFoundError:
        sessao.lock.release()
        raise HTTPException(404, "Conversa ou item não encontrado.") from None
    except ValidationError:
        sessao.lock.release()
        raise HTTPException(400, "Solicitação ChatKit inválida.") from None
    except BaseException:
        sessao.lock.release()
        raise


app.add_middleware(
    CORSMiddleware, allow_origins=origens, allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    # O ChatKit pode acrescentar cabeçalhos de cliente/versão nas requisições.
    # A lista de origens continua restrita; cabeçalhos não substituem autenticação.
    allow_headers=["*"],
)


# Opcional: Lightsail serve frontend e API na mesma URL.
frontend_dist = os.getenv("FRONTEND_DIST")
if frontend_dist:
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
