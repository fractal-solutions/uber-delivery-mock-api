import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root regardless of the current working directory,
# so the server picks up WEBHOOK_URL etc. even when started from elsewhere.
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")


def _positive_int(name: str, fallback: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _positive_float(name: str, fallback: float) -> float:
    try:
        value = float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


class Config:
    port: int = _positive_int("PORT", 3000)
    client_id: str = os.getenv("CLIENT_ID", "test-client-id")
    client_secret: str = os.getenv("CLIENT_SECRET", "test-client-secret")
    webhook_url: str = os.getenv("WEBHOOK_URL", "").strip()

    # Delivery simulation timing in milliseconds:
    # pending -> pickup -> pickup_complete -> dropoff -> delivered
    pending_ms: int = _positive_int("PENDING_MS", 10_000)
    pickup_ms: int = _positive_int("PICKUP_MS", 10_000)
    pickup_complete_ms: int = _positive_int("PICKUP_COMPLETE_MS", 20_000)
    dropoff_ms: int = _positive_int("DROPOFF_MS", 120_000)

    # Webhook cadence in milliseconds
    webhook_interval_ms: int = _positive_int("WEBHOOK_INTERVAL_MS", 20_000)
    courier_update_interval_ms: int = _positive_int("COURIER_UPDATE_INTERVAL_MS", 10_000)

    # Fee range when a delivery/quote has no explicit fee
    min_fee: float = _positive_float("MIN_FEE", 5.0)
    max_fee: float = _positive_float("MAX_FEE", 50.0)


config = Config()
