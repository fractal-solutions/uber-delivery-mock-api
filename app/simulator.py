import logging
import threading
import time

from app.config import config
from app.store import Delivery
from app.webhooks import send_webhook

logger = logging.getLogger("simulator")

TERMINAL_STATUSES = {"delivered", "canceled"}

# (status, duration_ms) - pending is the initial status set at creation
FLOW = [
    ("pickup", config.pending_ms),
    ("pickup_complete", config.pickup_ms),
    ("dropoff", config.pickup_complete_ms),
    ("delivered", config.dropoff_ms),
]


def _courier_imminent(status: str) -> bool:
    return status == "dropoff"


def build_payload(delivery: Delivery, kind: str, extra: dict | None = None) -> dict:
    data = {
        "courier": delivery.courier,
        "courier_imminent": _courier_imminent(delivery.status),
        "tracking_url": delivery.tracking_url,
        "status": delivery.status,
        "fee": delivery.fee,
    }
    if extra:
        data.update(extra)
    return {"delivery_id": delivery.id, "kind": kind, "data": data}


def _notify_status(delivery: Delivery) -> None:
    send_webhook(build_payload(delivery, "event.delivery_status"))


class DeliverySimulation(threading.Thread):
    """Simulates one delivery lifecycle on a background daemon thread."""

    def __init__(self, delivery: Delivery):
        super().__init__(name=f"sim-{delivery.id}", daemon=True)
        self.delivery = delivery
        self.stop_event = threading.Event()
        self._status_lock = threading.Lock()

    def run(self) -> None:
        delivery = self.delivery
        _notify_status(delivery)  # initial "pending" status event

        start = time.monotonic()
        transitions = []
        elapsed = 0.0
        for status, delay_ms in FLOW:
            elapsed += delay_ms / 1000
            transitions.append((start + elapsed, status))

        heartbeat_interval = config.webhook_interval_ms / 1000
        courier_interval = config.courier_update_interval_ms / 1000
        next_heartbeat = start + heartbeat_interval
        next_courier = start + courier_interval
        transition_index = 0

        while not self.stop_event.is_set():
            now = time.monotonic()
            candidates = [next_heartbeat, next_courier]
            if transition_index < len(transitions):
                candidates.append(transitions[transition_index][0])
            wait = max(0.0, min(candidates) - now)
            if self.stop_event.wait(wait):
                return

            now = time.monotonic()
            if transition_index < len(transitions) and now >= transitions[transition_index][0]:
                _, status = transitions[transition_index]
                transition_index += 1
                with self._status_lock:
                    if delivery.status in TERMINAL_STATUSES:
                        return
                    delivery.status = status
                logger.info("%s -> %s", delivery.id, status)
                _notify_status(delivery)
                if status == "delivered":
                    return
                continue

            if now >= next_heartbeat:
                next_heartbeat += heartbeat_interval
                with self._status_lock:
                    if delivery.status not in TERMINAL_STATUSES:
                        _notify_status(delivery)
                continue

            if now >= next_courier:
                next_courier += courier_interval
                with self._status_lock:
                    if delivery.status not in TERMINAL_STATUSES:
                        send_webhook(
                            build_payload(
                                delivery,
                                "event.courier_update",
                                {
                                    "pickup_eta": delivery.pickup_eta,
                                    "dropoff_eta": delivery.dropoff_eta,
                                },
                            )
                        )
                continue

    def cancel(self) -> None:
        with self._status_lock:
            if self.delivery.status in TERMINAL_STATUSES:
                return
            self.delivery.status = "canceled"
        self.stop_event.set()
        logger.info("%s -> canceled", self.delivery.id)
        _notify_status(self.delivery)


_simulations: dict[str, DeliverySimulation] = {}
_registry_lock = threading.Lock()


def start_delivery_simulation(delivery: Delivery) -> None:
    logger.info("Staring delivery simulation")
    simulation = DeliverySimulation(delivery)
    with _registry_lock:
        logger.info("Is this lock there?")
        _simulations[delivery.id] = simulation
    logger.info("%s simulation started", delivery.id)
    simulation.start()


def cancel_delivery_simulation(delivery: Delivery) -> None:
    with _registry_lock:
        simulation = _simulations.get(delivery.id)
    if simulation:
        simulation.cancel()
    else:
        # No simulation thread running; mark canceled directly.
        delivery.status = "canceled"
        _notify_status(delivery)
