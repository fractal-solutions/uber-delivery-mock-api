import json
import logging
import urllib.request

from app.config import config

logger = logging.getLogger("webhooks")


def send_webhook(payload: dict) -> None:
    if not config.webhook_url:
        return

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        config.webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
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
