# Uber Dummy Server

A small dummy Uber Deliveries API built with FastAPI (Python) for testing integrations.
All data is stored in memory, so the server resets on restart. No real Uber APIs are
called and there is no security - it only mimics the shapes and behaviors below.

## Requirements

- Python 3.10+

Install dependencies:

```bash
pip install -r requirements.txt
```

## Quick start

1. Make sure `.env` exists (a copy is already included). Set `WEBHOOK_URL` to the
   endpoint that should receive webhook events (leave empty to disable webhooks).
2. Run the server:

```bash
python run.py
```

The server listens on `http://localhost:3000` by default (change `PORT` in `.env`).
For development with auto-reload: `uvicorn app.main:app --reload`.

## Routes

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/auth` | Accepts form fields `client_id` and `client_secret` (fixed values from `.env`, default `test-client-id` / `test-client-secret`). Returns `{access_token, expires_in, token_type}` or `401`. |
| POST | `/deliveries` | Logs the form data, stores `manifest_items`, and starts the delivery simulation. Returns `201` with `{delivery_id, tracking_url, uber_response}`. |
| GET | `/deliveries/{id}` | Logs the request and returns `200` with `{delivery_id, status, fee, tracking_url, manifest_items}` (same manifest items the delivery was created with), or `404`. |
| POST | `/customers/{customer_id}/delivery_quotes` | Logs the form data and returns `201` with `{id, fee}`. |
| POST | `/customers/{customer_id}/cancel` | Logs the form data and returns `201` with `{status: "canceled", delivery_id}`. Accepts an optional `delivery_id` form field; without it, cancels the customer's most recent delivery. |
| any | `/customers/{customer_id}/{endpoint}` | Catch-all: logs the request. GET returns `200`, any other method returns `201`. |

## Sending form data

All request bodies are read as `application/x-www-form-urlencoded` (or
`multipart/form-data`), not JSON. Examples with `curl`:

```bash
curl -X POST http://localhost:3000/auth \
  -d client_id=test-client-id \
  -d client_secret=test-client-secret

curl -X POST http://localhost:3000/deliveries \
  -d customer_id=cust-123 \
  -d 'manifest_items=[{"name":"Pizza","quantity":2}]'

curl -X POST http://localhost:3000/customers/cust-123/cancel \
  -d delivery_id=delivery_...
```

`manifest_items` can be sent either as one JSON-encoded string (as above) or as
repeated form fields, one per item:

```bash
curl -X POST http://localhost:3000/deliveries \
  -d customer_id=cust-123 \
  -d 'manifest_items={"name":"Pizza","quantity":2}' \
  -d 'manifest_items={"name":"Salad","quantity":1}'
```

## Delivery simulation

Every delivery created through `POST /deliveries` automatically runs through:

`pending -> pickup -> pickup_complete -> dropoff -> delivered`

Default timing (override in `.env`):

| State | Duration |
| --- | --- |
| pending | `PENDING_MS` = 10 s |
| pickup | `PICKUP_MS` = 10 s |
| pickup_complete | `PICKUP_COMPLETE_MS` = 20 s |
| dropoff | `DROPOFF_MS` = 120 s |

Calling the cancel route moves the delivery to `canceled` and stops the simulation.

## Webhooks

Webhooks are POSTed to `WEBHOOK_URL` (from `.env`) as JSON:

```json
{
  "delivery_id": "delivery_...",
  "kind": "event.delivery_status",
  "data": {
    "courier": {
      "name": "Uber",
      "public_phone_info": "+1-555-010-0000",
      "lat": 37.7749,
      "lng": -122.4194,
      "vehicle_color": "Black",
      "vehicle_make": "Toyota",
      "vehicle_model": "Camry",
      "vehicle_license_plate": "ABC 1234",
      "vehicle_type": "sedan"
    },
    "courier_imminent": false,
    "tracking_url": "https://dummy-uber.local/tracking/delivery_...",
    "status": "pending",
    "fee": 17.13
  }
}
```

- `event.delivery_status` is sent when a delivery is created, on every status change,
  and as a heartbeat every `WEBHOOK_INTERVAL_MS` (default 20 s).
- `event.courier_update` is sent every `COURIER_UPDATE_INTERVAL_MS` (default 10 s)
  with `pickup_eta` and `dropoff_eta` (ISO date strings) added to `data`.

To capture webhooks locally while testing, run the included listener and point
`WEBHOOK_URL` at it:

```bash
python scripts/webhook_listener.py
```

It listens on `http://127.0.0.1:9099` and appends every received payload to
`webhook-captures.jsonl`.

## Troubleshooting

- **No webhooks?** The simulation starts automatically on `POST /deliveries`; no
  manual step is needed. If you are not receiving webhook events, check that
  `WEBHOOK_URL` is set in `.env` (it is empty by default). The server logs a
  warning at startup when webhooks are disabled and also logs when the
  simulation starts for each created delivery.
- **Started from another directory?** `.env` is loaded from the project root
  regardless of the current working directory.

## Notes

- Deliveries, manifest items, and quotes live only in memory.
- `courier_imminent` is `true` while the delivery is in the `dropoff` state.
- Fees are random within `MIN_FEE`/`MAX_FEE` when a request does not supply one.
