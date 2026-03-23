"""Webhook signature validators for common providers."""

import hashlib
import hmac
from typing import Optional


class SignatureValidator:
    """Validate webhook signatures from various providers."""

    @staticmethod
    def validate_github(payload: bytes, signature_header: str, secret: str) -> bool:
        """Validate GitHub webhook HMAC-SHA256 signature.

        GitHub sends: X-Hub-Signature-256: sha256=<hex-digest>
        """
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected_sig = signature_header[7:]  # strip "sha256="
        computed = hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, expected_sig)

    @staticmethod
    def validate_stripe(payload: bytes, signature_header: str, secret: str,
                        tolerance: int = 300) -> bool:
        """Validate Stripe webhook signature.

        Stripe sends: Stripe-Signature: t=<timestamp>,v1=<sig>,v0=<sig>
        """
        import time

        if not signature_header:
            return False

        parts = {}
        for item in signature_header.split(","):
            key, _, value = item.partition("=")
            parts.setdefault(key.strip(), []).append(value.strip())

        timestamp_str = parts.get("t", [None])[0]
        signatures = parts.get("v1", [])

        if not timestamp_str or not signatures:
            return False

        try:
            timestamp = int(timestamp_str)
        except ValueError:
            return False

        # Check tolerance
        if abs(time.time() - timestamp) > tolerance:
            return False

        # Compute expected signature
        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac.new(
            secret.encode("utf-8"), signed_payload, hashlib.sha256
        ).hexdigest()

        return any(hmac.compare_digest(expected, sig) for sig in signatures)

    @staticmethod
    def validate_shopify(payload: bytes, signature_header: str, secret: str) -> bool:
        """Validate Shopify webhook HMAC-SHA256 signature.

        Shopify sends: X-Shopify-Hmac-Sha256: <base64-digest>
        """
        import base64

        if not signature_header:
            return False

        computed = hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).digest()
        computed_b64 = base64.b64encode(computed).decode("utf-8")

        return hmac.compare_digest(computed_b64, signature_header)

    @staticmethod
    def validate_slack(payload: bytes, signature_header: str, secret: str,
                       timestamp_header: str = "", tolerance: int = 300) -> bool:
        """Validate Slack webhook signature.

        Slack sends: X-Slack-Signature: v0=<hex>, X-Slack-Request-Timestamp: <ts>
        """
        import time

        if not signature_header or not timestamp_header:
            return False

        try:
            ts = int(timestamp_header)
        except ValueError:
            return False

        if abs(time.time() - ts) > tolerance:
            return False

        sig_basestring = f"v0:{ts}:".encode() + payload
        computed = "v0=" + hmac.new(
            secret.encode("utf-8"), sig_basestring, hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(computed, signature_header)

    @classmethod
    def detect_provider(cls, headers: dict[str, str]) -> Optional[str]:
        """Detect webhook provider from headers."""
        h = {k.lower(): v for k, v in headers.items()}

        if "x-hub-signature-256" in h or "x-github-event" in h:
            return "github"
        if "stripe-signature" in h:
            return "stripe"
        if "x-shopify-hmac-sha256" in h:
            return "shopify"
        if "x-slack-signature" in h:
            return "slack"
        return None

    @classmethod
    def validate(cls, provider: str, payload: bytes, headers: dict[str, str],
                 secret: str) -> bool:
        """Validate signature for a detected provider."""
        h = {k.lower(): v for k, v in headers.items()}

        if provider == "github":
            return cls.validate_github(payload, h.get("x-hub-signature-256", ""), secret)
        elif provider == "stripe":
            return cls.validate_stripe(payload, h.get("stripe-signature", ""), secret)
        elif provider == "shopify":
            return cls.validate_shopify(payload, h.get("x-shopify-hmac-sha256", ""), secret)
        elif provider == "slack":
            return cls.validate_slack(
                payload, h.get("x-slack-signature", ""), secret,
                h.get("x-slack-request-timestamp", "")
            )
        return False
