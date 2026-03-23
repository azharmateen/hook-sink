"""FastAPI server that catches incoming webhooks."""

import json
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from .storage import WebhookStorage
from .validator import SignatureValidator

app = FastAPI(title="hook-sink", description="Local webhook catcher")
storage: Optional[WebhookStorage] = None


def get_storage() -> WebhookStorage:
    global storage
    if storage is None:
        storage = WebhookStorage()
    return storage


def set_storage(s: WebhookStorage):
    global storage
    storage = s


# --- API Endpoints ---

@app.get("/api/webhooks")
async def list_webhooks(limit: int = 50, offset: int = 0,
                        path: Optional[str] = None, method: Optional[str] = None,
                        body_contains: Optional[str] = None):
    """List captured webhooks with optional filtering."""
    s = get_storage()
    if path or method or body_contains:
        webhooks = s.search(path=path, method=method, body_contains=body_contains)
    else:
        webhooks = s.list_all(limit=limit, offset=offset)

    return {
        "webhooks": [
            {
                "id": w.id,
                "method": w.method,
                "path": w.path,
                "content_type": w.content_type,
                "source_ip": w.source_ip,
                "body_size": w.body_size,
                "timestamp": w.timestamp,
                "timestamp_iso": w.timestamp_iso,
            }
            for w in webhooks
        ],
        "total": s.count(),
    }


@app.get("/api/webhooks/{webhook_id}")
async def get_webhook(webhook_id: str):
    """Get full webhook details."""
    s = get_storage()
    w = s.get(webhook_id)
    if w is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {
        "id": w.id,
        "method": w.method,
        "path": w.path,
        "headers": w.headers,
        "body": w.body,
        "body_json": w.body_json,
        "query_params": w.query_params,
        "source_ip": w.source_ip,
        "content_type": w.content_type,
        "timestamp": w.timestamp,
        "timestamp_iso": w.timestamp_iso,
        "body_size": w.body_size,
        "provider": SignatureValidator.detect_provider(w.headers),
    }


@app.delete("/api/webhooks")
async def clear_webhooks():
    """Clear all captured webhooks."""
    s = get_storage()
    count = s.clear()
    return {"deleted": count}


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str):
    """Delete a single webhook."""
    s = get_storage()
    if s.delete(webhook_id):
        return {"deleted": True}
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.get("/api/stats")
async def stats():
    """Get storage stats."""
    s = get_storage()
    webhooks = s.list_all(limit=1000)
    methods = {}
    paths = {}
    for w in webhooks:
        methods[w.method] = methods.get(w.method, 0) + 1
        paths[w.path] = paths.get(w.path, 0) + 1
    return {
        "total": s.count(),
        "methods": methods,
        "top_paths": dict(sorted(paths.items(), key=lambda x: -x[1])[:10]),
    }


# --- Catch-all webhook receiver ---

@app.api_route("/hook/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def catch_webhook(request: Request, path: str):
    """Catch-all endpoint that captures any incoming webhook."""
    s = get_storage()
    body = (await request.body()).decode("utf-8", errors="replace")
    headers = dict(request.headers)
    query_params = dict(request.query_params)
    source_ip = request.client.host if request.client else "unknown"
    content_type = request.headers.get("content-type", "")

    webhook_id = s.store(
        method=request.method,
        path="/" + path,
        headers=headers,
        body=body,
        query_params=query_params,
        source_ip=source_ip,
        content_type=content_type,
    )

    return JSONResponse(
        {"received": True, "id": webhook_id},
        status_code=200,
    )


# Shorthand: POST to /webhook also works
@app.post("/webhook")
async def catch_root_webhook(request: Request):
    """Catch webhook at /webhook root."""
    s = get_storage()
    body = (await request.body()).decode("utf-8", errors="replace")
    headers = dict(request.headers)
    query_params = dict(request.query_params)
    source_ip = request.client.host if request.client else "unknown"
    content_type = request.headers.get("content-type", "")

    webhook_id = s.store(
        method=request.method,
        path="/webhook",
        headers=headers,
        body=body,
        query_params=query_params,
        source_ip=source_ip,
        content_type=content_type,
    )

    return JSONResponse(
        {"received": True, "id": webhook_id},
        status_code=200,
    )
