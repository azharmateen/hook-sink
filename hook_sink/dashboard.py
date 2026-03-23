"""Web dashboard for viewing and managing webhooks."""

import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from .server import app as api_app, get_storage
from .replayer import Replayer


# Mount dashboard on the same app
@api_app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the webhook dashboard."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
    with open(template_path) as f:
        html = f.read()
    return HTMLResponse(html)


@api_app.post("/api/replay/{webhook_id}")
async def replay_webhook(webhook_id: str, request: Request):
    """Replay a webhook to a target URL."""
    s = get_storage()
    data = await request.json()
    target = data.get("target", "http://localhost:3000")
    patches = data.get("patches", None)

    replayer = Replayer(s)
    result = replayer.replay(webhook_id, target, patches=patches)

    return {
        "success": result.success,
        "status_code": result.status_code,
        "elapsed_ms": round(result.elapsed_ms, 2),
        "response_body": result.response_body[:2000],
        "error": result.error,
    }
