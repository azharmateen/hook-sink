"""Replay engine: send captured webhooks to target URLs."""

import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .storage import Webhook, WebhookStorage


@dataclass
class ReplayResult:
    webhook_id: str
    target_url: str
    status_code: int
    response_body: str
    response_headers: dict[str, str]
    elapsed_ms: float
    success: bool
    error: Optional[str] = None


def apply_json_patch(body: str, patches: dict[str, Any]) -> str:
    """Apply simple JSON patches to webhook body.

    patches is a dict of JSON pointer paths to new values.
    Example: {"user.name": "new-name", "event": "push"}
    Supports dot-notation for nested keys.
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return body

    for path, value in patches.items():
        keys = path.split(".")
        obj = data
        for key in keys[:-1]:
            if isinstance(obj, dict) and key in obj:
                obj = obj[key]
            elif isinstance(obj, list):
                try:
                    obj = obj[int(key)]
                except (ValueError, IndexError):
                    break
            else:
                break
        else:
            final_key = keys[-1]
            if isinstance(obj, dict):
                obj[final_key] = value
            elif isinstance(obj, list):
                try:
                    obj[int(final_key)] = value
                except (ValueError, IndexError):
                    pass

    return json.dumps(data, indent=2)


class Replayer:
    """Replay captured webhooks to target URLs."""

    def __init__(self, storage: WebhookStorage):
        self.storage = storage

    def replay(self, webhook_id: str, target_url: str,
               patches: Optional[dict[str, Any]] = None,
               override_headers: Optional[dict[str, str]] = None,
               timeout: float = 30.0) -> ReplayResult:
        """Replay a webhook to a target URL.

        Args:
            webhook_id: ID of the stored webhook
            target_url: URL to send the webhook to
            patches: Optional dict of JSON path -> value patches to apply
            override_headers: Optional headers to override
            timeout: Request timeout in seconds
        """
        webhook = self.storage.get(webhook_id)
        if webhook is None:
            return ReplayResult(
                webhook_id=webhook_id,
                target_url=target_url,
                status_code=0,
                response_body="",
                response_headers={},
                elapsed_ms=0,
                success=False,
                error=f"Webhook {webhook_id} not found",
            )

        body = webhook.body
        if patches:
            body = apply_json_patch(body, patches)

        # Build headers, filtering out hop-by-hop headers
        skip_headers = {"host", "transfer-encoding", "connection", "keep-alive",
                        "content-length"}
        headers = {
            k: v for k, v in webhook.headers.items()
            if k.lower() not in skip_headers
        }
        if override_headers:
            headers.update(override_headers)

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(
                    method=webhook.method,
                    url=target_url + webhook.path,
                    headers=headers,
                    content=body.encode("utf-8") if body else None,
                )
                return ReplayResult(
                    webhook_id=webhook_id,
                    target_url=target_url + webhook.path,
                    status_code=response.status_code,
                    response_body=response.text,
                    response_headers=dict(response.headers),
                    elapsed_ms=response.elapsed.total_seconds() * 1000,
                    success=200 <= response.status_code < 400,
                )
        except httpx.RequestError as e:
            return ReplayResult(
                webhook_id=webhook_id,
                target_url=target_url + webhook.path,
                status_code=0,
                response_body="",
                response_headers={},
                elapsed_ms=0,
                success=False,
                error=str(e),
            )

    def replay_to_multiple(self, webhook_id: str, targets: list[str],
                           patches: Optional[dict[str, Any]] = None) -> list[ReplayResult]:
        """Replay a webhook to multiple targets."""
        return [self.replay(webhook_id, target, patches) for target in targets]
