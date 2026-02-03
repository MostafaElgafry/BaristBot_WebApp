# Machine User API

## Overview

The Machine User API allows external systems (POS, kiosks, mobile apps) to place coffee orders programmatically. The robot processes **one order at a time** -- additional orders are placed in a FIFO queue and dispatched automatically when the current order completes.

All endpoints require an `X-API-Key` header for authentication.

---

## Authentication

Every request must include the API key in the header:

```
X-API-Key: <your-api-key>
```

The key is configured on the server via the `MACHINE_API_KEY` environment variable.
Default: `egyrobot8000`

**Responses without a valid key:**

| Scenario         | HTTP Status | Body                            |
|------------------|-------------|---------------------------------|
| Missing header   | 403         | `{"detail": "Missing X-API-Key header."}` |
| Wrong key        | 403         | `{"detail": "Invalid API key."}`          |

---

## Endpoints

### 1. Place an Order

```
POST /api/machine/order/
```

The caller only needs to send the **recipe name** and an **external order ID**. The system looks up the recipe and resolves all robot parameters automatically (dose, grind grade, doser number, recipe number).

**Request body:**

```json
{
  "order_name": "Espresso",
  "order_id": "POS-001"
}
```

| Field        | Type   | Required | Description                              |
|--------------|--------|----------|------------------------------------------|
| `order_name` | string | yes      | Recipe name (must match an active Recipe) |
| `order_id`   | string | yes      | External order ID for your tracking       |

**Response (201 Created):**

```json
{
  "order_id": 1,
  "external_order_id": "POS-001",
  "order_name": "Espresso",
  "status": "processing",
  "message": "ACK"
}
```

The `status` field will be one of:

| Status       | Meaning                                            |
|--------------|----------------------------------------------------|
| `processing` | Sent to the robot immediately (machine was idle)   |
| `queued`     | Machine is busy; order added to the queue           |
| `error`      | Failed to send to robot (see `message` for details) |

---

### 2. Complete an Order

```
POST /api/machine/order/<order_id>/complete/
```

Call this when the robot finishes making the drink. It marks the order as completed and **automatically dispatches the next queued order** if one exists.

> `<order_id>` is the internal `order_id` returned when the order was placed (not the external one).

**Response (200 OK):**

```json
{
  "success": true,
  "completed_order_id": 1,
  "next_order": {
    "order_id": 2,
    "status": "processing",
    "message": "ACK"
  }
}
```

If there are no queued orders, `next_order` will be `null`.

---

### 3. View Queue Status

```
GET /api/machine/queue/
```

Returns the currently active order and all queued orders.

**Response (200 OK):**

```json
{
  "active_order": {
    "id": 1,
    "external_order_id": "POS-001",
    "order_name": "Espresso",
    "dose_grams": 18,
    "grind_grade": 5,
    "doser_number": 1,
    "recipe_number": 2,
    "status": "processing",
    "status_display": "Processing",
    "source": "machine",
    "response_message": "ACK",
    "created_at": "2026-01-31T12:00:00Z"
  },
  "queue_length": 2,
  "queued_orders": [
    {
      "id": 2,
      "external_order_id": "POS-002",
      "order_name": "Latte",
      "status": "queued",
      ...
    },
    {
      "id": 3,
      "external_order_id": "POS-003",
      "order_name": "Cappuccino",
      "status": "queued",
      ...
    }
  ]
}
```

If the machine is idle, `active_order` will be `null` and `queue_length` will be `0`.

---

## How the Queue Works

```
  New Order ──> Is machine idle?
                   │
              YES  │   NO
               │       │
               v       v
          Send to   Add to queue
           robot    (status: queued)
        (status:       │
        processing)    │
               │       │
               v       │
          Order        │
         completes     │
               │       │
               v       │
          Next in  <───┘
           queue?
           │    │
        YES    NO
         │      │
         v      v
       Send   Machine
      to bot   idle
```

- Only **one order** is active at any time.
- Queued orders are processed in **FIFO** order (oldest first).
- Completing an order via the `/complete/` endpoint triggers the next dispatch automatically.

---

## Recipe Configuration

Each recipe must be configured with its robot parameters **before** it can be ordered through the API.

### Required setup:

1. **Create/update a Recipe** with robot parameters:
   - `dose_grams` -- dose weight (1-200g)
   - `grind_grade` -- grind coarseness (1-11)
   - `doser_number` -- which doser to use (1-4)

2. **Assign the Recipe to a ToneMachineButton** -- this determines the `recipe_number` (1-4) sent to the robot.

This can be done via:
- Django Admin panel
- `PUT /api/recipes/<id>/` (requires authenticated user with technician/manager role)
- `PUT /api/tone-buttons/<id>/` (requires authenticated user with technician/manager role)

### Example: Configure "Espresso"

```bash
# Update recipe with robot parameters (requires auth token)
curl -X PATCH http://192.168.1.240:8000/api/recipes/1/ \
  -H "Authorization: Token <user-token>" \
  -H "Content-Type: application/json" \
  -d '{"dose_grams": 18, "grind_grade": 5, "doser_number": 1}'

# Assign to tone machine button 2 (requires auth token)
curl -X PATCH http://192.168.1.240:8000/api/tone-buttons/2/ \
  -H "Authorization: Token <user-token>" \
  -H "Content-Type: application/json" \
  -d '{"recipe": 1}'
```

Now `POST /api/machine/order/` with `"order_name": "Espresso"` will use dose=18g, grind=5, doser=1, recipe_number=2.

---

## Error Handling

| Error                                          | HTTP Status | When                                             |
|------------------------------------------------|-------------|--------------------------------------------------|
| `Missing X-API-Key header.`                    | 403         | No `X-API-Key` header sent                       |
| `Invalid API key.`                             | 403         | Wrong API key value                               |
| `No active recipe found with name '...'`       | 400         | `order_name` doesn't match any active recipe      |
| `Recipe '...' is not assigned to any active tone machine button.` | 400 | Recipe exists but not mapped to a button |
| `Order #N is not active (status: ...)`         | 400         | Trying to complete a non-active order             |

---

## Full Example Flow

```bash
API_KEY="egyrobot8000"
URL="http://192.168.1.240:8000/api/machine"

# 1. Place first order -- goes directly to robot
curl -X POST "$URL/order/" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"order_name": "Espresso", "order_id": "POS-001"}'
# -> {"order_id":1, "status":"processing", ...}

# 2. Place second order while machine is busy -- gets queued
curl -X POST "$URL/order/" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"order_name": "Latte", "order_id": "POS-002"}'
# -> {"order_id":2, "status":"queued", ...}

# 3. Check queue
curl -H "X-API-Key: $API_KEY" "$URL/queue/"
# -> {"active_order":{id:1,...}, "queue_length":1, "queued_orders":[{id:2,...}]}

# 4. Robot finishes order 1 -- complete it, order 2 auto-dispatches
curl -X POST "$URL/order/1/complete/" \
  -H "X-API-Key: $API_KEY"
# -> {"success":true, "completed_order_id":1, "next_order":{"order_id":2,"status":"processing",...}}
```

---

## Files Reference

| File                          | Purpose                                         |
|-------------------------------|--------------------------------------------------|
| `barista_app/order_queue.py`  | Queue service -- enqueue, complete, dispatch logic |
| `barista_app/api_views.py`    | API views (MachineOrderAPIView, etc.)            |
| `barista_app/api_urls.py`     | URL routing for `/api/machine/*`                 |
| `barista_app/serializers.py`  | Input/output serializers for machine API         |
| `barista_app/models.py`       | ManualOrder (queue fields), Recipe (robot params) |
| `barista_project/settings.py` | `MACHINE_API_KEY` configuration                  |

---

## Environment Variables

| Variable          | Default                          | Description                    |
|-------------------|----------------------------------|--------------------------------|
| `MACHINE_API_KEY` | `egyrobot8000`                   | API key for machine endpoints  |
