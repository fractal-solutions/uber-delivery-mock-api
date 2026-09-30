import hashlib
import hmac
import json
import logging
import urllib.request

from app.config import config

logger = logging.getLogger("webhooks")


def sign_payload(data: bytes, signing_key: str) -> str:
    """HMAC-SHA256 hex digest, matching Uber's webhook signature scheme."""
    return hmac.new(signing_key.encode("utf-8"), data, hashlib.sha256).hexdigest()


def send_webhook(payload: dict) -> None:
    if not config.webhook_url:
        return

    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.webhook_signing_key:
        headers["X-Uber-Signature"] = sign_payload(data, config.webhook_signing_key)
    request = urllib.request.Request(
        config.webhook_url,
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            logger.info(
                "delivery_id=%s kind=%s -> HTTP %s",
                payload["delivery_id"],
                payload["kind"],
                response.status,
            )
    except Exception as exc:  # webhooks must never break the server
        logger.error(
            "delivery_id=%s kind=%s failed: %s",
            payload["delivery_id"],
            payload["kind"],
            exc,
        )
