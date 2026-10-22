import os

if os.environ.get("WORKSHOP_SERVICE") == "supervisor":
    import uvicorn

    from santander_demo.supervisor_server import app

    uvicorn.run(app, host="0.0.0.0", port=8080, access_log=False)
else:
    from santander_demo.mcp_server import mcp

    mcp.run(transport="streamable-http")
