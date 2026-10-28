from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse

from chatkit.server import StreamingResult
from servidor_chatkit import servidor

from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()


@app.post("/chatkit")
async def chatkit_endpoint(request: Request):
    body = await request.body()

    resultado = await servidor.process(
        body,
        {"user_id": "usuario-teste"}
    )

    if isinstance(resultado, StreamingResult):
        return StreamingResponse(
            resultado,
            media_type="text/event-stream"
        )

    return Response(
        content=resultado.json,
        media_type="application/json"
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)