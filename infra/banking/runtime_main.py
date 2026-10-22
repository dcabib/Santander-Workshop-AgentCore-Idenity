"""Entry point empacotado: um Runtime por LOB e outro para o agente."""

import importlib
import os

from santander_demo.banking.spec import LOBS

service = os.environ["BANKING_SERVICE"]
if service == "agent":
    from santander_demo.banking.agent import app

    app.run()
else:
    module = importlib.import_module("santander_demo.banking.lobs." + LOBS[service]["module"])
    if os.environ.get("FEDERATED_IDENTITY"):
        from santander_demo.federation.runtime_identity import register

        register(module.mcp)
    module.mcp.run(transport="streamable-http")
