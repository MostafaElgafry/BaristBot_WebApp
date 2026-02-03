"""
Django REST Framework API Views for Barista Robot Control System.
"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from django.contrib.auth import login, logout
from django.utils import timezone
from django.db.models import Sum, Count
from datetime import timedelta

from .models import (
    UserProfile, CoffeeType, Grinder, Dozer, Recipe,
    ToneMachineButton, Inventory, ManualOrder, SystemConfiguration,
    SystemSettings, ActivityLog, AnalyticsDaily
)
from .serializers import (
    UserProfileSerializer, UserCreateSerializer, LoginSerializer,
    CoffeeTypeSerializer, GrinderSerializer, DozerSerializer,
    RecipeSerializer, ToneMachineButtonSerializer, InventorySerializer,
    ManualOrderSerializer, MachineOrderInputSerializer,
    MachineOrderResponseSerializer, SystemConfigurationSerializer,
    SystemSettingsSerializer, ActivityLogSerializer, AnalyticsDailySerializer,
    DashboardSerializer
)
from .robot_control import send_manual_order, check_robot_connection, wait_for_order_completion, check_pre_use
from .order_queue import enqueue_order, complete_order, get_queue_info


class IsManagerPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'manager'


class CanConfigureEquipmentPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        return request.user.is_authenticated and request.user.can_configure_equipment()


class CanSendOrdersPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.can_send_manual_orders()


class LoginAPIView(APIView):
    """Handle user authentication."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            login(request, user)
            user.last_activity = timezone.now()
            user.save(update_fields=['last_activity'])

            # Create or get token
            token, _ = Token.objects.get_or_create(user=user)

            # Log activity
            ActivityLog.objects.create(
                action_type='user_login',
                description=f"User {user.username} logged in",
                user=user
            )

            return Response({
                'success': True,
                'token': token.key,
                'user': UserProfileSerializer(user).data
            })
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class LogoutAPIView(APIView):
    """Handle user logout."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ActivityLog.objects.create(
            action_type='user_logout',
            description=f"User {request.user.username} logged out",
            user=request.user
        )
        logout(request)
        return Response({'success': True})


class DashboardAPIView(APIView):
    """Get dashboard data."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Get warnings from inventory
        warnings = []
        for item in Inventory.objects.all():
            if item.is_warning:
                warnings.append({
                    'type': 'inventory',
                    'message': f"{item.name} is low ({item.current_level}%)",
                    'severity': 'warning' if item.current_level > 10 else 'critical'
                })

        # Check robot connection
        robot_connected, robot_status = check_robot_connection()
        if not robot_connected:
            warnings.append({
                'type': 'system',
                'message': f"Robot not connected: {robot_status}",
                'severity': 'critical'
            })

        # Get recent activity
        recent_activity = ActivityLog.objects.all()[:10]

        # Get system status
        settings = SystemSettings.get_settings()
        last_backup = SystemConfiguration.objects.first()

        return Response({
            'user': UserProfileSerializer(request.user).data,
            'system_status': {
                'last_backup': last_backup.created_at if last_backup else None,
                'last_sync': settings.last_sync,
                'robot_version': settings.robot_version,
                'firmware_version': settings.firmware_version,
            },
            'warnings': warnings,
            'warnings_count': len(warnings),
            'recent_activity': ActivityLogSerializer(recent_activity, many=True).data,
            'robot_connected': robot_connected,
            'robot_status': robot_status if robot_connected else None,
        })


class UserViewSet(viewsets.ModelViewSet):
    """CRUD for users (manager only)."""
    queryset = UserProfile.objects.all()
    permission_classes = [IsManagerPermission]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserProfileSerializer

    def perform_destroy(self, instance):
        ActivityLog.objects.create(
            action_type='config_changed',
            description=f"User {instance.username} deleted",
            user=self.request.user
        )
        instance.delete()


class CoffeeTypeViewSet(viewsets.ModelViewSet):
    """CRUD for coffee types."""
    queryset = CoffeeType.objects.all()
    serializer_class = CoffeeTypeSerializer
    permission_classes = [CanConfigureEquipmentPermission]


class GrinderViewSet(viewsets.ModelViewSet):
    """CRUD for grinders."""
    queryset = Grinder.objects.all()
    serializer_class = GrinderSerializer
    permission_classes = [CanConfigureEquipmentPermission]

    def perform_create(self, serializer):
        instance = serializer.save()
        ActivityLog.objects.create(
            action_type='config_changed',
            description=f"Grinder '{instance.name}' created",
            user=self.request.user,
            metadata={'grinder_id': instance.id}
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        ActivityLog.objects.create(
            action_type='config_changed',
            description=f"Grinder '{instance.name}' updated",
            user=self.request.user,
            metadata={'grinder_id': instance.id}
        )


class DozerViewSet(viewsets.ModelViewSet):
    """CRUD for dozers."""
    queryset = Dozer.objects.all()
    serializer_class = DozerSerializer
    permission_classes = [CanConfigureEquipmentPermission]

    def perform_create(self, serializer):
        instance = serializer.save()
        ActivityLog.objects.create(
            action_type='config_changed',
            description=f"Dozer '{instance.name}' created",
            user=self.request.user,
            metadata={'dozer_id': instance.id}
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        ActivityLog.objects.create(
            action_type='config_changed',
            description=f"Dozer '{instance.name}' updated",
            user=self.request.user,
            metadata={'dozer_id': instance.id}
        )


class RecipeViewSet(viewsets.ModelViewSet):
    """CRUD for recipes."""
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    permission_classes = [CanConfigureEquipmentPermission]


class ToneMachineButtonViewSet(viewsets.ModelViewSet):
    """CRUD for tone machine buttons."""
    queryset = ToneMachineButton.objects.all()
    serializer_class = ToneMachineButtonSerializer
    permission_classes = [CanConfigureEquipmentPermission]

    def perform_update(self, serializer):
        instance = serializer.save()
        ActivityLog.objects.create(
            action_type='config_changed',
            description=f"Tone Machine Button {instance.button_number} updated",
            user=self.request.user,
            metadata={'button_number': instance.button_number}
        )


class InventoryViewSet(viewsets.ModelViewSet):
    """CRUD for inventory."""
    queryset = Inventory.objects.all()
    serializer_class = InventorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        instance = serializer.save()
        ActivityLog.objects.create(
            action_type='inventory_updated',
            description=f"Inventory '{instance.name}' updated",
            user=self.request.user,
            metadata={
                'item_id': instance.id,
                'current_level': instance.current_level
            }
        )

    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        """Bulk update inventory items."""
        items_data = request.data.get('items', [])
        updated = []
        for item_data in items_data:
            try:
                item = Inventory.objects.get(id=item_data['id'])
                if 'current_level' in item_data:
                    item.current_level = item_data['current_level']
                if 'current_count' in item_data:
                    item.current_count = item_data['current_count']
                if 'warning_threshold' in item_data:
                    item.warning_threshold = item_data['warning_threshold']
                item.save()
                updated.append(item.id)
            except Inventory.DoesNotExist:
                pass

        ActivityLog.objects.create(
            action_type='inventory_updated',
            description=f"Bulk inventory update ({len(updated)} items)",
            user=request.user
        )
        return Response({'success': True, 'updated': updated})


class ManualOrderViewSet(viewsets.ModelViewSet):
    """CRUD for manual orders."""
    queryset = ManualOrder.objects.all()
    serializer_class = ManualOrderSerializer
    permission_classes = [CanSendOrdersPermission]

    def get_queryset(self):
        return ManualOrder.objects.all()[:50]  # Last 50 orders

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create order record
        order = ManualOrder.objects.create(
            dose_grams=serializer.validated_data['dose_grams'],
            grind_grade=serializer.validated_data['grind_grade'],
            doser_number=serializer.validated_data.get('doser_number', 1),
            recipe_number=serializer.validated_data['recipe_number'],
            status='pending',
            created_by=request.user
        )

        # Send to robot
        success, message = send_manual_order(
            int(order.dose_grams),
            order.grind_grade,
            order.doser_number,
            order.recipe_number
        )

        if success:
            order.status = 'ack'
            order.response_message = message
            ActivityLog.objects.create(
                action_type='order_sent',
                description=f"Manual order #{order.id} acknowledged by robot",
                user=request.user,
                metadata={
                    'order_id': order.id,
                    'dose': order.dose_grams,
                    'grind_grade': order.grind_grade,
                    'doser_number': order.doser_number,
                    'recipe': order.recipe_number
                }
            )
        else:
            order.status = 'error'
            order.response_message = message
            ActivityLog.objects.create(
                action_type='order_failed',
                description=f"Manual order #{order.id} failed: {message}",
                user=request.user,
                metadata={'order_id': order.id, 'error': message}
            )

        order.save()
        return Response(
            ManualOrderSerializer(order).data,
            status=status.HTTP_201_CREATED
        )


class SystemConfigurationViewSet(viewsets.ModelViewSet):
    """CRUD for system configurations."""
    queryset = SystemConfiguration.objects.all()
    serializer_class = SystemConfigurationSerializer
    permission_classes = [CanConfigureEquipmentPermission]

    def perform_create(self, serializer):
        # Gather current config data
        config_data = {}

        if serializer.validated_data.get('include_grinders', True):
            config_data['grinders'] = list(Grinder.objects.values())

        if serializer.validated_data.get('include_dozers', True):
            config_data['dozers'] = list(Dozer.objects.values())

        if serializer.validated_data.get('include_tone_machine', True):
            config_data['tone_buttons'] = list(ToneMachineButton.objects.values())

        if serializer.validated_data.get('include_inventory_thresholds', True):
            config_data['inventory'] = list(
                Inventory.objects.values('id', 'name', 'warning_threshold')
            )

        if serializer.validated_data.get('include_display_preferences', False):
            settings = SystemSettings.get_settings()
            config_data['display'] = {
                'theme': settings.theme,
                'brightness': settings.brightness,
                'volume': settings.volume,
                'language': settings.language,
            }

        serializer.save(created_by=self.request.user, config_data=config_data)

    @action(detail=True, methods=['post'])
    def load(self, request, pk=None):
        """Load a saved configuration."""
        config = self.get_object()
        loaded = []

        if config.include_grinders and 'grinders' in config.config_data:
            for data in config.config_data['grinders']:
                Grinder.objects.update_or_create(
                    id=data['id'],
                    defaults={k: v for k, v in data.items() if k != 'id'}
                )
            loaded.append('grinders')

        if config.include_dozers and 'dozers' in config.config_data:
            for data in config.config_data['dozers']:
                Dozer.objects.update_or_create(
                    id=data['id'],
                    defaults={k: v for k, v in data.items() if k != 'id'}
                )
            loaded.append('dozers')

        if config.include_tone_machine and 'tone_buttons' in config.config_data:
            for data in config.config_data['tone_buttons']:
                ToneMachineButton.objects.update_or_create(
                    id=data['id'],
                    defaults={k: v for k, v in data.items() if k != 'id'}
                )
            loaded.append('tone_buttons')

        if config.include_inventory_thresholds and 'inventory' in config.config_data:
            for data in config.config_data['inventory']:
                Inventory.objects.filter(id=data['id']).update(
                    warning_threshold=data['warning_threshold']
                )
            loaded.append('inventory_thresholds')

        if config.include_display_preferences and 'display' in config.config_data:
            settings = SystemSettings.get_settings()
            display = config.config_data['display']
            settings.theme = display.get('theme', settings.theme)
            settings.brightness = display.get('brightness', settings.brightness)
            settings.volume = display.get('volume', settings.volume)
            settings.language = display.get('language', settings.language)
            settings.save()
            loaded.append('display_preferences')

        ActivityLog.objects.create(
            action_type='config_changed',
            description=f"Configuration '{config.name}' loaded",
            user=request.user,
            metadata={'loaded': loaded}
        )

        return Response({'success': True, 'loaded': loaded})


class SystemSettingsAPIView(APIView):
    """Get/Update system settings."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        settings = SystemSettings.get_settings()
        return Response(SystemSettingsSerializer(settings).data)

    def patch(self, request):
        settings = SystemSettings.get_settings()
        serializer = SystemSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AnalyticsAPIView(APIView):
    """Get analytics data."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()

        # Get or create today's analytics
        analytics, _ = AnalyticsDaily.objects.get_or_create(date=today)

        # Get recent analytics
        last_7_days = AnalyticsDaily.objects.filter(
            date__gte=today - timedelta(days=7)
        )

        # Calculate KPIs
        today_orders = ManualOrder.objects.filter(
            created_at__date=today,
            status='ack'
        ).count()

        # Get hourly distribution
        hourly = {}
        for hour in range(24):
            count = ManualOrder.objects.filter(
                created_at__date=today,
                created_at__hour=hour,
                status='ack'
            ).count()
            hourly[str(hour).zfill(2)] = count

        # Find peak hour
        peak_hour = max(hourly, key=hourly.get) if hourly else None

        # Recipe distribution
        recipe_dist = ManualOrder.objects.filter(
            created_at__date=today,
            status='ack'
        ).values('recipe_number').annotate(count=Count('id'))

        recipe_distribution = {str(r['recipe_number']): r['count'] for r in recipe_dist}

        # Top recipe
        top_recipe = max(recipe_distribution, key=recipe_distribution.get) if recipe_distribution else None

        return Response({
            'today': {
                'total_cups': today_orders,
                'avg_per_hour': round(today_orders / max(timezone.now().hour, 1), 1),
                'peak_hour': peak_hour,
                'top_recipe': top_recipe,
            },
            'hourly': hourly,
            'recipe_distribution': recipe_distribution,
            'last_7_days': AnalyticsDailySerializer(last_7_days, many=True).data,
        })


class RobotStatusAPIView(APIView):
    """Check robot connection status."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        connected, status_msg = check_robot_connection()
        return Response({
            'connected': connected,
            'status': status_msg
        })


class PreUseCheckAPIView(APIView):
    """Check delivery cup and coffee server presence before sending an order."""
    permission_classes = [CanSendOrdersPermission]

    def post(self, request):
        result = check_pre_use()
        http_status = status.HTTP_200_OK if result["ok"] else status.HTTP_409_CONFLICT
        return Response(result, status=http_status)


class OrderCompletionAPIView(APIView):
    """Wait for order completion from robot."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        """Wait for completion notification and update order status."""
        try:
            order = ManualOrder.objects.get(id=order_id)
        except ManualOrder.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        # Only wait for orders that are processing
        if order.status != 'processing':
            return Response({
                'order_id': order.id,
                'status': order.status,
                'message': f'Order is not processing (status: {order.status})'
            })

        # Get timeout from request (default 60 seconds)
        timeout = float(request.data.get('timeout', 60.0))

        # Wait for completion
        success, message = wait_for_order_completion(timeout=timeout)

        if success:
            order.status = 'completed'
            order.response_message = message
            order.save()
            ActivityLog.objects.create(
                action_type='order_completed',
                description=f"Manual order #{order.id} completed",
                user=request.user,
                metadata={'order_id': order.id, 'completion_message': message}
            )
        else:
            # Keep as processing if timeout, set error if actual error
            if 'Timeout' not in message:
                order.status = 'error'
                order.response_message = message
                order.save()

        return Response({
            'order_id': order.id,
            'status': order.status,
            'message': message,
            'completed': success
        })


# ─── Machine User API ───────────────────────────────────────────────


class MachineAPIKeyPermission(permissions.BasePermission):
    """Validates the X-API-Key header against MACHINE_API_KEY setting."""

    def has_permission(self, request, view):
        from django.conf import settings
        api_key = request.headers.get('X-API-Key', '')
        if not api_key:
            self.message = 'Missing X-API-Key header.'
            return False
        if api_key != settings.MACHINE_API_KEY:
            self.message = 'Invalid API key.'
            return False
        return True


class MachineOrderAPIView(APIView):
    """
    Machine-to-machine API for placing orders.

    Accepts only `order_name` (recipe name) and `order_id` (external ID).
    The system resolves all robot parameters (dose, grind, doser, recipe number)
    from the Recipe configuration.

    The machine can only process one order at a time.
    If the machine is busy, the order is added to a queue.
    When the current order completes, the next queued order
    is automatically dispatched.
    """
    authentication_classes = []
    permission_classes = [MachineAPIKeyPermission]

    def post(self, request):
        """Place a new order. Returns immediately with status (processing or queued)."""
        serializer = MachineOrderInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order_name = serializer.validated_data['order_name']
        external_order_id = serializer.validated_data['order_id']

        # Look up recipe and resolve all robot parameters
        recipe = Recipe.objects.get(name__iexact=order_name, is_active=True)
        recipe_number = recipe.get_recipe_number()
        if recipe_number is None:
            return Response({
                'error': f"Recipe '{recipe.name}' is not assigned to any active tone machine button."
            }, status=status.HTTP_400_BAD_REQUEST)

        order = ManualOrder.objects.create(
            external_order_id=external_order_id,
            order_name=recipe.name,
            dose_grams=recipe.dose_grams,
            grind_grade=recipe.grind_grade,
            doser_number=recipe.doser_number,
            recipe_number=recipe_number,
            status='pending',
            source='machine',
            created_by=None,
        )

        order_status, message = enqueue_order(order)
        order.refresh_from_db()

        return Response({
            'order_id': order.id,
            'external_order_id': order.external_order_id,
            'order_name': order.order_name,
            'status': order.status,
            'message': message,
        }, status=status.HTTP_201_CREATED)


class MachineOrderCompleteAPIView(APIView):
    """
    Callback endpoint for marking an order as completed.

    When called, it completes the given order and automatically
    dispatches the next queued order to the robot.
    """
    authentication_classes = []
    permission_classes = [MachineAPIKeyPermission]

    def post(self, request, order_id):
        """Mark order as completed, dispatch next queued order."""
        result = complete_order(order_id)

        if not result['success']:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)


class MachineQueueStatusAPIView(APIView):
    """
    Returns the current queue state: active order and queued orders.
    """
    authentication_classes = []
    permission_classes = [MachineAPIKeyPermission]

    def get(self, request):
        info = get_queue_info()
        active = info['active_order']
        queued = info['queued_orders']

        return Response({
            'active_order': MachineOrderResponseSerializer(active).data if active else None,
            'queue_length': info['queue_length'],
            'queued_orders': MachineOrderResponseSerializer(queued, many=True).data,
        })


class MachineDataSnapshotAPIView(APIView):
    """
    Returns a full data snapshot for machine clients.

    Useful for clients that need to sync available configuration/state
    before sending orders.
    """
    authentication_classes = []
    permission_classes = [MachineAPIKeyPermission]

    def get(self, request):
        recipes = list(
            Recipe.objects.filter(is_active=True)
            .order_by('name')
            .values('id', 'name')
        )
        return Response({'recipes': recipes})
