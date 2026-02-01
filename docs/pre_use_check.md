# Pre-Use Check

## Overview

Before every manual order is sent to the robot, the web app performs a pre-use check to verify that the physical setup is ready. The check confirms two conditions:

1. **Delivery cup is present** on the platform.
2. **At least one of the four coffee servers** is present.

If either condition is not met, the order is blocked and the user sees an error message explaining what is missing.

## Serial Protocol

### Request

The web app sends a `CHECK` command over serial:

```
CHECK\n
```

### Response

The robot responds with a comma-separated string:

```
data,<cup>,<server1>,<server2>,<server3>,<server4>\n
```

| Field     | Index | Description                        | Values            |
|-----------|-------|------------------------------------|-------------------|
| `data`    | 0     | Fixed prefix                       | Always `"data"`   |
| `cup`     | 1     | Delivery cup presence              | `1` = present, `0` = absent |
| `server1` | 2     | Coffee server 1 presence           | `1` = present, `0` = absent |
| `server2` | 3     | Coffee server 2 presence           | `1` = present, `0` = absent |
| `server3` | 4     | Coffee server 3 presence           | `1` = present, `0` = absent |
| `server4` | 5     | Coffee server 4 presence           | `1` = present, `0` = absent |

**Example:** `data,1,0,0,1,0\n` means the cup is present, servers 1-3 are absent, and server 4 is present. This would pass the check.

## Validation Rules

| Condition | Rule |
|-----------|------|
| Delivery cup | Must be `1` (present) |
| Coffee servers | At least one of the four must be `1` |

Both conditions must be satisfied for the order to proceed.

## API Endpoint

### `POST /api/robot/pre-use-check/`

**Permission:** Same as order submission (Supervisor, Technician, or Manager).

**Request body:** None required.

**Response (200 OK - check passed):**

```json
{
  "ok": true,
  "cup_present": true,
  "servers": [true, false, false, true],
  "message": "Pre-use check passed"
}
```

**Response (409 Conflict - check failed):**

```json
{
  "ok": false,
  "cup_present": false,
  "servers": [false, false, false, false],
  "message": "Delivery cup is missing. No coffee server detected"
}
```

## Frontend Behavior

When the user clicks **Send** in the confirmation modal:

1. The button text changes to **"Checking..."**.
2. The app calls `POST /api/robot/pre-use-check/`.
3. **If the check fails:** A red error alert appears below the form showing the specific problem (e.g., "Delivery cup is missing"). The order is not sent.
4. **If the check passes:** The button text changes to **"Sending..."** and the order proceeds normally.

## Demo Mode

When `ROBOT_DEMO_MODE` is enabled, the pre-use check always returns all items as present and the order proceeds without serial communication.

## Files

| File | What was added |
|------|----------------|
| `barista_app/robot_control.py` | `send_check()` method and `check_pre_use()` function |
| `barista_app/api_views.py` | `PreUseCheckAPIView` class |
| `barista_app/api_urls.py` | Route registration for `/api/robot/pre-use-check/` |
| `barista_app/templates/barista/manual_order.html` | Frontend gating logic before order submission |
