"""
Order Queue Service for Barista Robot Control System.

Manages a single-order-at-a-time queue for the machine.
When the machine is busy, new orders are queued. When the current
order completes, the next queued order is automatically dispatched.
"""
import threading
import logging

from .models import ManualOrder, ActivityLog
from .robot_control import send_manual_order

logger = logging.getLogger(__name__)

_queue_lock = threading.Lock()


def _get_active_order():
    """Return the currently active order (sent/ack/processing), or None."""
    return ManualOrder.objects.filter(
        status__in=['sent', 'ack', 'processing']
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


def enqueue_order(order):
    """
    Attempt to process an order immediately, or queue it.

    If no order is currently active, sends this order to the robot.
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
    """Send an order to the robot and update its status."""
    success, message = send_manual_order(
        int(order.dose_grams),
        order.grind_grade,
        order.doser_number,
        order.recipe_number,
    )

    if success:
        order.status = 'processing'
        order.response_message = message
        order.save()
        ActivityLog.objects.create(
            action_type='order_sent',
            description=f"Order #{order.id} sent to robot via {order.source} API",
            user=order.created_by,
            metadata={
                'order_id': order.id,
                'dose': order.dose_grams,
                'grind_grade': order.grind_grade,
                'doser_number': order.doser_number,
                'recipe': order.recipe_number,
                'source': order.source,
            }
        )
        logger.info(f"Order #{order.id} dispatched to robot: {message}")
        return 'processing', message
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
        logger.error(f"Order #{order.id} dispatch failed: {message}")
        return 'error', message


def complete_order(order_id):
    """
    Mark an order as completed and dispatch the next queued order.

    Returns dict with completion info and next order info (if any).
    """
    with _queue_lock:
        try:
            order = ManualOrder.objects.get(id=order_id)
        except ManualOrder.DoesNotExist:
            return {'success': False, 'error': 'Order not found'}

        if order.status not in ('sent', 'ack', 'processing'):
            return {
                'success': False,
                'error': f'Order #{order_id} is not active (status: {order.status})'
            }

        order.status = 'completed'
        order.save()
        ActivityLog.objects.create(
            action_type='order_completed',
            description=f"Order #{order.id} completed",
            user=order.created_by,
            metadata={'order_id': order.id, 'source': order.source}
        )
        logger.info(f"Order #{order.id} completed")

        result = {
            'success': True,
            'completed_order_id': order.id,
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
