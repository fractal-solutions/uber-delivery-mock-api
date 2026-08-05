import random
import threading
import uuid
from datetime import datetime, timedelta, timezone

from app.config import config
import logging


DEFAULT_COURIER = {
    "name": "Uber",
    "public_phone_info": "+1-555-010-0000",
    "lat": 37.7749,
    "lng": -122.4194,
    "vehicle_color": "Black",
    "vehicle_make": "Toyota",
    "vehicle_model": "Camry",
    "vehicle_license_plate": "ABC 1234",
    "vehicle_type": "sedan",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("uber-dummy")


class Delivery:
    def __init__(self, body: dict):
        self.id = f"delivery_{uuid.uuid4()}"
        self.customer_id = body.get("customer_id") if isinstance(body.get("customer_id"), str) else None
        self.status = "pending"
        fee = body.get("fee")
        self.fee = fee if isinstance(fee, (int, float)) and fee > 0 else random_fee()
        self.tracking_url = f"https://dummy-uber.local/tracking/{self.id}"
        manifest_items = body.get("manifest_items")
        self.manifest_items = manifest_items if isinstance(manifest_items, list) else []
        self.request_body = body
        self.courier = dict(DEFAULT_COURIER)

        now = datetime.now(timezone.utc)
        self.created_at = now.isoformat()
        self.pickup_eta = (now + timedelta(milliseconds=config.pending_ms)).isoformat()
        self.dropoff_eta = (
            now
            + timedelta(
                milliseconds=(
                    config.pending_ms
                    + config.pickup_ms
                    + config.pickup_complete_ms
                    + config.dropoff_ms
                )
            )
        ).isoformat()

    def to_dict(self) -> dict:
        return {
            "delivery_id": self.id,
            "status": self.status,
            "fee": self.fee,
            "tracking_url": self.tracking_url,
            "manifest_items": self.manifest_items,
            "customer_id": self.customer_id,
            "created_at": self.created_at,
        }


def random_fee() -> float:
    return round(config.min_fee + random.random() * (config.max_fee - config.min_fee), 2)


_deliveries: dict[str, Delivery] = {}
_lock = threading.Lock()


def create_delivery(body: object) -> Delivery:
    logger.info("Creating delivery")
    record = body if isinstance(body, dict) else {}
    with _lock:
        logger.info("Getting lock when creating delivery")
        delivery = Delivery(record)
        _deliveries[delivery.id] = delivery
        return delivery


def get_delivery(delivery_id: str) -> Delivery | None:
    with _lock:
        return _deliveries.get(delivery_id)


def most_recent_delivery_for_customer(customer_id: str) -> Delivery | None:
    with _lock:
        for delivery in reversed(list(_deliveries.values())):
            if delivery.customer_id == customer_id:
                return delivery
    return None
