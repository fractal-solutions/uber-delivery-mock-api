import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import config
from app.simulator import cancel_delivery_simulation, start_delivery_simulation
from app.store import create_delivery, get_delivery, most_recent_delivery_for_customer, random_fee

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("uber-dummy")

app = FastAPI(title="Uber Dummy Server", version="1.0.0")

if config.webhook_url:
    logger.info("webhooks enabled - events will be posted to %s", config.webhook_url)
else:
    logger.warning(
        "WEBHOOK_URL is not set in .env - webhook events will be skipped "
        "(delivery simulation still runs)"
    )


def _coerce_form_value(value: object) -> object:
    """Keep plain strings as-is, but parse strings that look like JSON
    (e.g. a JSON-encoded manifest_items array) into real objects."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return str(value)


async def _form_body(request: Request) -> dict:
    """Read a form body (application/x-www-form-urlencoded or multipart/form-data).
    Repeated fields are collected into lists."""
    form = await request.form()
    body: dict[str, object] = {}
    for key in form.keys():
        values = form.getlist(key)
        if len(values) > 1:
            body[key] = [_coerce_form_value(value) for value in values]
        else:
            body[key] = _coerce_form_value(values[0])
    return body


async def _json_or_form_body(request: Request) -> dict:
    """Read either a JSON body (what the real Uber API accepts) or a form body
    (kept for backwards compatibility with the original dummy server)."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return await _form_body(request)


def _log_request(request: Request, body: object = None) -> None:
    logger.info(
        json.dumps(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "method": request.method,
                "url": str(request.url),
                "path_params": request.path_params,
                "query": dict(request.query_params),
                "body": body,
            },
            default=str,
        )
    )


@app.get("/")
def root() -> dict:
    return {
        "service": "uber-dummy-server",
        "webhooks": {
            "enabled": bool(config.webhook_url),
            "url": config.webhook_url or None,
        },
        "routes": [
            "POST /oauth/v2/token (Uber OAuth)",
            "POST /v1/customers/{customer_id}/delivery_quotes (Uber Direct)",
            "POST /v1/customers/{customer_id}/deliveries (Uber Direct)",
            "GET /v1/customers/{customer_id}/deliveries/{delivery_id} (Uber Direct)",
            "POST /v1/customers/{customer_id}/deliveries/{delivery_id}/cancel (Uber Direct)",
            "POST /auth",
            "POST /deliveries",
            "GET /deliveries/{id}",
            "POST /customers/{customer_id}/delivery_quotes",
            "POST /customers/{customer_id}/cancel",
            "GET|POST /customers/{customer_id}/{endpoint} (catch-all)",
        ],
    }


def _issue_token(body: dict) -> dict:
    if body.get("client_id") == config.client_id and body.get("client_secret") == config.client_secret:
        return {
            "access_token": config.access_token,
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    raise HTTPException(
        status_code=401,
        detail={"error": "invalid_client", "error_description": "Invalid client credentials."},
    )


@app.post("/oauth/v2/token")
@app.post("/v1/oauth/v2/token")
async def oauth_token(request: Request) -> dict:
    body = await _form_body(request)
    _log_request(request, body)
    return _issue_token(body)


@app.post("/auth")
async def auth(request: Request) -> dict:
    body = await _form_body(request)
    _log_request(request, body)
    return _issue_token(body)


# --- Uber Direct v1 routes: mirror the real Uber API (JSON bodies) ---


@app.post("/v1/customers/{customer_id}/delivery_quotes", status_code=201)
async def uber_delivery_quotes(customer_id: str, request: Request) -> dict:
    body = await _json_or_form_body(request)
    _log_request(request, body)
    return {
        "id": f"quote_{uuid.uuid4().hex[:8]}",
        "fee": random_fee(),
        "currency": "KES",
        "duration": 1800,
        "dropoff_eta": datetime.now(timezone.utc).isoformat(),
        "expires_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/customers/{customer_id}/deliveries", status_code=201)
async def uber_create_delivery(customer_id: str, request: Request) -> dict:
    body = await _json_or_form_body(request)
    _log_request(request, body)
    body.setdefault("customer_id", customer_id)
    delivery = create_delivery(body)
    start_delivery_simulation(delivery)
    return delivery.to_uber_dict()


@app.get("/v1/customers/{customer_id}/deliveries/{delivery_id}")
async def uber_get_delivery(customer_id: str, delivery_id: str, request: Request) -> dict:
    delivery = get_delivery(delivery_id)
    if delivery is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "delivery_not_found", "delivery_id": delivery_id},
        )
    _log_request(request)
    return delivery.to_uber_dict()


@app.post("/v1/customers/{customer_id}/deliveries/{delivery_id}/cancel")
async def uber_cancel_delivery(customer_id: str, delivery_id: str, request: Request) -> dict:
    body = await _json_or_form_body(request)
    _log_request(request, body)
    delivery = get_delivery(delivery_id)
    if delivery is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "delivery_not_found", "delivery_id": delivery_id},
        )
    cancel_delivery_simulation(delivery)
    return delivery.to_uber_dict()


@app.post("/customers/{customer_id}/deliveries", status_code=201)
async def create_delivery_route(request: Request) -> dict:
    body = await _form_body(request)
    _log_request(request, body)
    delivery = create_delivery(body)
    start_delivery_simulation(delivery)
    return {
        "id": delivery.id,
        "tracking_url": delivery.tracking_url,
        "uber_response": {"status": delivery.status, **delivery.request_body},
    }


@app.get("/deliveries/{delivery_id}")
async def get_delivery_route(delivery_id: str, request: Request) -> dict:
    delivery = get_delivery(delivery_id)
    if delivery is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "delivery_not_found", "delivery_id": delivery_id},
        )
    _log_request(request)
    return delivery.to_dict()


@app.post("/customers/{customer_id}/delivery_quotes", status_code=201)
async def delivery_quotes(customer_id: str, request: Request) -> dict:
    body = await _form_body(request)
    _log_request(request, body)
    return {"id": f"quote_{uuid.uuid4().hex[:8]}", "fee": random_fee()}


@app.post("/customers/{customer_id}/cancel", status_code=201)
async def cancel(customer_id: str, request: Request) -> dict:
    body = await _form_body(request)
    _log_request(request, body)
    delivery_id = body.get("delivery_id") if isinstance(body.get("delivery_id"), str) else None
    delivery = get_delivery(delivery_id) if delivery_id else most_recent_delivery_for_customer(customer_id)
    if delivery:
        cancel_delivery_simulation(delivery)
    return {"status": "canceled", "delivery_id": delivery.id if delivery else None}


# Catch-all for /customers/{customer_id}/{endpoint} (must be registered last).
@app.api_route(
    "/customers/{customer_id}/{endpoint}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def catch_all(customer_id: str, endpoint: str, request: Request) -> JSONResponse:
    body = await _form_body(request)
    _log_request(request, body)
    return JSONResponse(
        status_code=200 if request.method == "GET" else 201,
        content={
            "message": "ok" if request.method == "GET" else "created",
            "customer_id": customer_id,
            "endpoint": endpoint,
        },
    )
