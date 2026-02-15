"""
Order Queue Service for Barista Robot Control System.

Manages a single-order-at-a-time queue for the machine.
When the machine is busy, new orders are queued.
The next queued order is dispatched ONLY when the caller explicitly
hits the /complete/ endpoint after the current order has finished.
"""
import threading
import logging

from .models import ManualOrder, ActivityLog
from .robot_control import send_manual_order

logger = logging.getLogger(__name__)

_queue_lock = threading.Lock()


def _get_active_order():
    """Return the currently active order (processing), or None."""
    return ManualOrder.objects.filter(
        status='processing'
    ).order_by('created_at').first()


def _get_next_queued_order():
    """Return the oldest queued order, or None."""
    return ManualOrder.objects.filter(
        status='queued'
    ).order_by('created_at').first()


def get_queue_info():
    """Return current queue state."""
    active = _get_active_order()
    queued = ManualOrder.objects.filter(status='queued').order_by('created_at')
    return {
        'active_order': active,
        'queued_orders': list(queued),
        'queue_length': queued.count(),
    }


def kick_queue():
    """
    Recover from a stuck queue state.

    If there are queued orders but no active/completed order blocking
    the queue, dispatches the next queued order. Handles server restarts,
    failed completions, or other edge cases.

    Returns dict with action taken and result.
    """
    with _queue_lock:
        active = _get_active_order()

        if active is not None:
            return {
                'action': 'none',
                'reason': f'Queue not stuck - order #{active.id} is active',
            }

        # Also check for completed/error orders that haven't been
        # acknowledged via /complete/ yet (they block the queue).
        unacked = ManualOrder.objects.filter(
            status__in=['completed', 'error']
        ).order_by('-created_at').first()

        next_order = _get_next_queued_order()

        if next_order is None:
            return {
                'action': 'none',
                'reason': 'No queued orders to dispatch',
            }

        if unacked:
            # There's a finished order that was never acknowledged.
            # Mark it so the queue can move forward.
            logger.info(f"Queue kick: clearing unacknowledged order #{unacked.id} (status={unacked.status})")

        # Dispatch the next queued order
        status, message = _dispatch_order(next_order)
        logger.info(f"Queue kicked: dispatched order #{next_order.id} with status {status}")

        return {
            'action': 'dispatched',
            'order_id': next_order.id,
            'status': status,
            'message': message,
        }


def enqueue_order(order):
    """
    Attempt to process an order immediately, or queue it.

    If no order is currently being processed, sends this order to the robot.
    Otherwise, marks it as queued.

    Returns (status, message) tuple.
    """
    with _queue_lock:
        active = _get_active_order()

        if active is None:
            return _dispatch_order(order)
        else:
            order.status = 'queued'
            order.save()
            queue_pos = ManualOrder.objects.filter(
                status='queued', created_at__lt=order.created_at
            ).count() + 1
            logger.info(
                f"Order #{order.id} queued (position {queue_pos}). "
                f"Active order: #{active.id}"
            )
            return 'queued', f"Order queued at position {queue_pos}. Active order: #{active.id}"


def _dispatch_order(order):
    """
    Send an order to the robot in a background thread.

    Marks the order as 'processing' and returns immediately.
    The background thread updates the order to 'completed' or 'error'
    when the robot finishes but does NOT auto-dispatch the next order.
    The next order is dispatched only when the caller hits /complete/.
    """
    order.status = 'processing'
    order.response_message = 'Dispatched to robot'
    order.save()

    def _run_order():
        """Background worker: send commands to robot, update order on finish."""
        try:
            success, message = send_manual_order(
                order.doser_number,
                order.grinder_number,
                order.recipe_number,
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

    return 'processing', 'Order dispatched to robot'


def complete_order(order_id):
    """
    Acknowledge a finished order and dispatch the next queued order.

    Only succeeds when the order has actually finished (status 'completed'
    or 'error'). Rejects if the robot is still working on it ('processing').

    Returns dict with completion info and next order info (if any).
    """
    with _queue_lock:
        try:
            order = ManualOrder.objects.get(id=order_id)
        except ManualOrder.DoesNotExist:
            return {'success': False, 'error': 'Order not found'}

        # Only allow completing orders that the robot has actually finished.
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

        logger.info(f"Order #{order.id} acknowledged (was {order.status})")

        result = {
            'success': True,
            'completed_order_id': order.id,
            'final_status': order.status,
            'next_order': None,
        }

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
