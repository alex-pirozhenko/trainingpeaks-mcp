import os
import subprocess
import sys

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()

PORT = 8000
PROXY_PORT = 8001
PROXY_URL = f"http://127.0.0.1:{PROXY_PORT}"

# Global reference to the mcp-proxy process
mcp_proxy_proc = None


@app.on_event("startup")
async def startup_event():
    global mcp_proxy_proc
    # Launch mcp-proxy in the background
    # (mcp-proxy --port 8001 --host 127.0.0.1 -- tp-mcp serve)
    cmd = [
        "mcp-proxy",
        f"--port={PROXY_PORT}",
        "--host=127.0.0.1",
        "--",
        "tp-mcp",
        "serve",
    ]
    print(f"Starting mcp-proxy: {' '.join(cmd)}")
    mcp_proxy_proc = subprocess.Popen(
        cmd,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


@app.on_event("shutdown")
async def shutdown_event():
    global mcp_proxy_proc
    if mcp_proxy_proc:
        print("Terminating mcp-proxy...")
        mcp_proxy_proc.terminate()
        mcp_proxy_proc.wait()


@app.get("/health")
async def health():
    global mcp_proxy_proc
    if mcp_proxy_proc is None or mcp_proxy_proc.poll() is not None:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "mcp-proxy is not running"},
        )
    return {"status": "ok", "service": "tp-mcp-shim"}


@app.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata():
    resource_url = os.environ.get(
        "TP_MCP_RESOURCE_URL", "https://tp.mcp.pirozhenko.me"
    )
    auth_server_url = os.environ.get(
        "TP_MCP_AUTH_SERVER_URL", "https://auth.pirozhenko.me"
    )
    return {
        "resource": resource_url,
        "authorization_servers": [auth_server_url],
    }


@app.api_route("/mcp-unauthorized", methods=["GET", "POST", "DELETE"])
async def mcp_unauthorized():
    resource_url = os.environ.get(
        "TP_MCP_RESOURCE_URL", "https://tp.mcp.pirozhenko.me"
    )
    return JSONResponse(
        status_code=401,
        headers={
            "WWW-Authenticate": (
                'Bearer error="invalid_token", '
                f'resource_metadata="{resource_url}/.well-known/oauth-protected-resource"'
            )
        },
        content={
            "error": "unauthorized",
            "error_description": "Bearer token required",
        },
    )


# Reverse proxy all other requests to mcp-proxy
@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS"],
)
async def reverse_proxy(request: Request, path: str):
    async with httpx.AsyncClient(base_url=PROXY_URL, timeout=120.0) as client:
        url = f"/{path}"
        if request.query_params:
            url += f"?{request.query_params}"

        req_headers = dict(request.headers)
        # Remove host header to avoid routing confusion in localhost
        req_headers.pop("host", None)

        req_body = await request.body()

        # We need to support streaming for SSE (text/event-stream)
        # httpx supports streaming responses via send()
        proxy_req = client.build_request(
            method=request.method,
            url=url,
            headers=req_headers,
            content=req_body,
        )

        resp = await client.send(proxy_req, stream=True)

        # If it's an SSE response, return a StreamingResponse
        if resp.headers.get("content-type", "").startswith("text/event-stream"):
            return StreamingResponse(
                resp.aiter_raw(),
                status_code=resp.status_code,
                headers=dict(resp.headers),
            )
        else:
            # httpx.Response.read() is the sync-client method; a response
            # obtained via AsyncClient.send(..., stream=True) must be drained
            # with aread() instead, or it raises "Attempted to call a sync
            # iterator on an async stream." on every non-SSE request.
            await resp.aread()
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
            )
