"""
Order Queue Service for Barista Robot Control System.

Manages a single-order-at-a-time queue for the machine.
When the machine is busy, new orders are queued.
The next queued order is dispatched ONLY when the caller explicitly
hits the /complete/ endpoint after the current order has finished.

Order lifecycle:
  pending → waiting_for_cup → processing → completed/error → ack (via /complete/)
  pending → queued → waiting_for_cup → processing → completed/error → ack (via /complete/)

The queue is BLOCKED when any order is in 'waiting_for_cup', 'processing',
'completed', or 'error' status. Only after /complete/ moves it to 'ack'
is the queue free to dispatch the next order.
"""
import threading
import logging

from .models import ManualOrder, ActivityLog
from .robot_control import send_manual_order

logger = logging.getLogger(__name__)


def _get_active_order():
    """Return the currently active order (processing), or None."""
    return ManualOrder.objects.filter(
        status='processing'
    ).order_by('created_at').first()


def _get_waiting_for_cup_order():
    """Return the order currently waiting for a delivery cup, or None."""
    return ManualOrder.objects.filter(
        status='waiting_for_cup'
    ).order_by('created_at').first()


def _get_unacked_order():
    """Return the most recent finished-but-unacknowledged order, or None.

    These are orders that finished (completed/error) but haven't been
    acknowledged via /complete/ yet. They block the queue.
    """
    return ManualOrder.objects.filter(
        status__in=['completed', 'error']
    ).order_by('-created_at').first()


def _get_next_queued_order():
    """Return the oldest queued order, or None."""
    return ManualOrder.objects.filter(
        status='queued'
    ).order_by('created_at').first()


def _is_queue_blocked():
    """Check if the queue is blocked by an active, waiting-for-cup, or unacknowledged order."""
    if _get_active_order() is not None:
        return True
    if _get_waiting_for_cup_order() is not None:
        return True
    if _get_unacked_order() is not None:
        return True
    return False


def get_queue_info():
    """Return current queue state."""
    active = _get_active_order()
    waiting_cup = _get_waiting_for_cup_order()
    unacked = _get_unacked_order()
    queued = ManualOrder.objects.filter(status='queued').order_by('created_at')
    current = active or waiting_cup or unacked
    return {
        'active_order': active,
        'waiting_for_cup_order': waiting_cup,
        'unacked_order': unacked,
        'current_order': current,
        'queued_orders': list(queued),
        'queue_length': queued.count(),
    }


def kick_queue():
    """
    Recover from a stuck queue state.

    If there are queued orders but no active order blocking the queue,
    acknowledges any unacked orders and dispatches the next queued order.

    Returns dict with action taken and result.
    """
    active = _get_active_order()
    waiting_cup = _get_waiting_for_cup_order()

    if active is not None:
        return {
            'action': 'none',
            'reason': f'Queue not stuck - order #{active.id} is active',
        }

    if waiting_cup is not None:
        return {
            'action': 'none',
            'reason': f'Queue not stuck - order #{waiting_cup.id} is waiting for cup',
        }

    next_order = _get_next_queued_order()

    if next_order is None:
        return {
            'action': 'none',
            'reason': 'No queued orders to dispatch',
        }

    # Clear any unacknowledged orders so the queue can move forward.
    unacked = _get_unacked_order()
    if unacked:
        logger.info(
            f"Queue kick: acknowledging order #{unacked.id} "
            f"(status={unacked.status})"
        )
        unacked.status = 'ack'
        unacked.save()

    # Dispatch the next queued order
    status, message = _dispatch_order(next_order)
    logger.info(
        f"Queue kicked: dispatched order #{next_order.id} "
        f"with status {status}"
    )

    return {
        'action': 'dispatched',
        'order_id': next_order.id,
        'status': status,
        'message': message,
    }


def enqueue_order(order):
    """
    Attempt to process an order immediately, or queue it.

    The order is dispatched immediately ONLY when:
      - No order is currently being processed, AND
      - No finished order is waiting for /complete/, AND
      - No orders are already waiting in the queue.

    Otherwise it is queued. Queued orders are dispatched exclusively
    via the /complete/ endpoint.

    Returns (status, message) tuple.
    """
    active = _get_active_order()
    waiting_cup = _get_waiting_for_cup_order()
    unacked = _get_unacked_order()
    has_queued = ManualOrder.objects.filter(status='queued').exists()

    if active is None and waiting_cup is None and unacked is None and not has_queued:
        return _dispatch_order(order)
    else:
        order.status = 'queued'
        order.save()
        queue_pos = ManualOrder.objects.filter(
            status='queued', created_at__lt=order.created_at
        ).count() + 1
        if active:
            blocker = f'order #{active.id} (processing)'
        elif waiting_cup:
            blocker = f'order #{waiting_cup.id} (waiting for cup)'
        elif unacked:
            blocker = f'order #{unacked.id} (waiting for /complete/)'
        else:
            blocker = 'queued orders ahead'
        logger.info(
            f"Order #{order.id} queued (position {queue_pos}). "
            f"Blocked by: {blocker}"
        )
        return 'queued', f"Order queued at position {queue_pos}"


def _dispatch_order(order):
    """
    Send an order to the robot in a background thread.

    Initially marks the order as 'waiting_for_cup'. The background thread
    polls the cup sensor. Once verified, transitions to 'processing' and
    sends robot commands. Updates to 'completed' or 'error' when done.
    The next order is dispatched only when the caller hits /complete/.
    """
    order.status = 'waiting_for_cup'
    order.response_message = 'Checking delivery cup...'
    order.save()

    def _run_order():
        """Background worker: poll cup, send commands to robot, update order."""
        try:
            from .robot_control import is_demo_mode, _check_cup_with_polling

            # ── Phase 1: Cup check with polling ─────────────
            if not is_demo_mode():
                pre = _check_cup_with_polling(order_id=order.id)

                if not pre.get('cup_present'):
                    order.refresh_from_db()
                    order.status = 'error'
                    order.response_message = (
                        f"Cup not detected after timeout: "
                        f"{pre.get('message', 'Delivery cup missing')}"
                    )
                    order.save()
                    ActivityLog.objects.create(
                        action_type='order_failed',
                        description=(
                            f"Order #{order.id} failed: delivery cup "
                            f"not detected after timeout"
                        ),
                        user=order.created_by,
                        metadata={
                            'order_id': order.id,
                            'error': 'cup_check_timeout',
                        }
                    )
                    logger.error(
                        f"Order #{order.id} failed: cup not detected"
                    )
                    return

            # ── Phase 2: Transition to processing ───────────
            order.refresh_from_db()
            order.status = 'processing'
            order.response_message = 'Cup verified, dispatching to robot'
            order.save()

            # ── Phase 3: Execute robot commands ─────────────
            success, message = send_manual_order(
                order.doser_number,
                order.grinder_number,
                order.recipe_number,
                order.dose_grams,
                order.grind_grade,
                order_id=order.id,
            )

            # Refresh from DB in case it was modified
            order.refresh_from_db()

            if success:
                order.status = 'completed'
                order.response_message = message
                order.save()
                ActivityLog.objects.create(
                    action_type='order_completed',
                    description=f"Order #{order.id} completed via {order.source} API",
                    user=order.created_by,
                    metadata={
                        'order_id': order.id,
                        'dose': order.dose_grams,
                        'grind_grade': order.grind_grade,
                        'doser_number': order.doser_number,
                        'grinder_number': order.grinder_number,
                        'recipe': order.recipe_number,
                        'source': order.source,
                    }
                )
                logger.info(f"Order #{order.id} completed: {message}")
                # Do NOT dispatch next order here.
                # The caller must hit /complete/ to advance the queue.
            else:
                order.status = 'error'
                order.response_message = message
                order.save()
                ActivityLog.objects.create(
                    action_type='order_failed',
                    description=f"Order #{order.id} failed: {message}",
                    user=order.created_by,
                    metadata={'order_id': order.id, 'error': message}
                )
                logger.error(f"Order #{order.id} failed: {message}")
                # Do NOT dispatch next order here.
                # The caller must hit /complete/ to advance the queue.
        except Exception as e:
            logger.exception(f"[ERROR] Background order #{order.id} crashed: {e}")
            try:
                order.refresh_from_db()
                order.status = 'error'
                order.response_message = f"Unexpected error: {e}"
                order.save()
            except Exception:
                pass

    worker = threading.Thread(target=_run_order, daemon=True)
    worker.start()

    return 'waiting_for_cup', 'Checking delivery cup'


def complete_order(order_id):
    """
    Acknowledge a finished order and dispatch the next queued order.

    Only succeeds when the order has actually finished (status 'completed'
    or 'error'). Rejects if the robot is still working on it ('processing').

    Moves the order to 'ack' status so the queue knows it's been
    acknowledged and is free to dispatch the next order.

    Returns dict with completion info and next order info (if any).
    """
    try:
        order = ManualOrder.objects.get(id=order_id)
    except ManualOrder.DoesNotExist:
        return {'success': False, 'error': 'Order not found'}

    # Only allow completing orders that the robot has actually finished.
    if order.status == 'waiting_for_cup':
        return {
            'success': False,
            'error': (
                f'Order #{order_id} is waiting for the delivery cup. '
                f'Place the cup and wait for processing to complete.'
            ),
        }

    if order.status == 'processing':
        return {
            'success': False,
            'error': (
                f'Order #{order_id} is still being processed by the robot. '
                f'Wait until it finishes before calling complete.'
            ),
        }

    if order.status not in ('completed', 'error'):
        return {
            'success': False,
            'error': f'Order #{order_id} cannot be completed (status: {order.status})',
        }

    # Mark as acknowledged — this unblocks the queue.
    final_status = order.status
    order.status = 'ack'
    order.save()

    logger.info(f"Order #{order.id} acknowledged (was {final_status})")

    result = {
        'success': True,
        'completed_order_id': order.id,
        'final_status': final_status,
        'next_order': None,
    }

    # Only dispatch next if no other order is already processing or waiting.
    # This prevents two orders running simultaneously.
    already_processing = _get_active_order()
    already_waiting = _get_waiting_for_cup_order()
    if already_processing:
        logger.info(
            f"Order #{already_processing.id} is already processing, "
            f"not dispatching next after completing #{order.id}"
        )
        return result
    if already_waiting:
        logger.info(
            f"Order #{already_waiting.id} is waiting for cup, "
            f"not dispatching next after completing #{order.id}"
        )
        return result

    # Dispatch next queued order
    next_order = _get_next_queued_order()
    if next_order:
        next_status, next_message = _dispatch_order(next_order)
        result['next_order'] = {
            'order_id': next_order.id,
            'status': next_status,
            'message': next_message,
        }
        logger.info(
            f"Next order #{next_order.id} dispatched after "
            f"completing #{order.id}: {next_status}"
        )

    return result
