from django.apps import AppConfig


class BaristaAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'barista_app'
    verbose_name = 'Barista Robot Control'

    def ready(self):
        """Recover stuck queue on server startup."""
        import sys
        # Skip during migrations or other management commands
        if any(cmd in sys.argv for cmd in ['migrate', 'makemigrations', 'collectstatic', 'check']):
            return

        # Only run for runserver or gunicorn/uwsgi (production servers)
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv[0] or 'uwsgi' in sys.argv[0]:
            import threading
            # Defer 2 seconds to let Django fully initialize
            threading.Timer(2.0, self._recover_stuck_queue).start()

    def _recover_stuck_queue(self):
        """Called after startup to recover any stuck orders."""
        try:
            from .order_queue import kick_queue
            import logging
            logger = logging.getLogger(__name__)

            result = kick_queue()
            if result['action'] == 'dispatched':
                logger.info(f"Startup: auto-dispatched stuck order #{result['order_id']}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"Queue recovery skipped: {e}")
