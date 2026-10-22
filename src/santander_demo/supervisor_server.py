"""Supervisor HTTP para AgentCore Runtime; orquestração determinística e auditável."""

import json
import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from santander_demo.cloud import CloudWorkshop
from santander_demo.config import Environment
from santander_demo.contracts import CLIENTE, DemoError

USER_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-User-Token"


async def invoke(request: Request):
    # Runtime valida inbound; Gateway verifica novamente o token para sua audiência.
    token = request.headers.get(USER_HEADER, "")
    if not token:
        return JSONResponse({"error": "DELEGATION_REQUIRED"}, status_code=401)
    try:
        body = await request.json()
        if set(body) != {"cliente_id"} or body["cliente_id"] != CLIENTE:
            return JSONResponse({"error": "SCHEMA_INVALID"}, status_code=400)
        config = Environment.model_validate_json(os.environ["WORKSHOP_CONFIG"])
        workshop = CloudWorkshop(config)
        result = await workshop.analyze(token, body["cliente_id"])
        return JSONResponse(result)
    except DemoError as exc:
        return JSONResponse({"error": exc.code}, status_code=403)
    except Exception as exc:
        # HTTP/SDK exceptions podem carregar detalhes sensíveis. Registrar só o tipo.
        print(json.dumps({"event": "supervisor_error", "type": type(exc).__name__}))
        return JSONResponse({"error": "INTEGRATION_FAILED"}, status_code=502)


async def ping(request):
    return JSONResponse({"status": "Healthy"})


app = Starlette(routes=[Route("/invocations", invoke, methods=["POST"]), Route("/ping", ping)])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080, access_log=False)
