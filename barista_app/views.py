"""
Django views for Barista Robot Control System HTML pages.
"""
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone

from .models import (
    UserProfile, Grinder, Dozer, ToneMachineButton, Recipe,
    CoffeeType, Inventory, ManualOrder, SystemConfiguration,
    SystemSettings, ActivityLog
)
from .robot_control import check_robot_connection


def barista_display(request):
    """Barista display screen - read-only monitoring."""
    warnings = []
    for item in Inventory.objects.all():
        if item.is_warning:
            warnings.append({
                'name': item.name,
                'level': item.current_level,
                'severity': 'critical' if item.current_level <= 10 else 'warning'
            })

    robot_connected, _ = check_robot_connection()

    return render(request, 'barista/display.html', {
        'warnings': warnings,
        'robot_connected': robot_connected,
        'current_time': timezone.now(),
    })


def login_view(request):
    """User login page."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            user.last_activity = timezone.now()
            user.save(update_fields=['last_activity'])

            ActivityLog.objects.create(
                action_type='user_login',
                description=f"User {user.username} logged in",
                user=user
            )
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')

    return render(request, 'barista/login.html')


@login_required
def logout_view(request):
    """User logout."""
    ActivityLog.objects.create(
        action_type='user_logout',
        description=f"User {request.user.username} logged out",
        user=request.user
    )
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    """Main dashboard."""
    warnings = []
    for item in Inventory.objects.all():
        if item.is_warning:
            warnings.append({
                'name': item.name,
                'level': item.current_level,
                'type': item.get_item_type_display()
            })

    robot_connected, robot_status = check_robot_connection()
    recent_activity = ActivityLog.objects.all()[:10]
    last_backup = SystemConfiguration.objects.first()

    return render(request, 'barista/dashboard.html', {
        'warnings': warnings,
        'warnings_count': len(warnings),
        'robot_connected': robot_connected,
        'robot_status': robot_status,
        'recent_activity': recent_activity,
        'last_backup': last_backup,
    })


@login_required
def equipment_overview(request):
    """Equipment overview hub."""
    grinders = Grinder.objects.filter(is_active=True)
    dozers = Dozer.objects.filter(is_active=True)
    tone_buttons = ToneMachineButton.objects.all()

    return render(request, 'barista/equipment/overview.html', {
        'grinders': grinders,
        'grinders_count': grinders.count(),
        'dozers': dozers,
        'dozers_count': dozers.count(),
        'tone_buttons': tone_buttons,
    })


@login_required
def grinders_list(request):
    """Grinder list view."""
    grinders = Grinder.objects.all()
    coffee_types = CoffeeType.objects.filter(is_active=True)

    return render(request, 'barista/equipment/grinders.html', {
        'grinders': grinders,
        'coffee_types': coffee_types,
    })


@login_required
def dozers_list(request):
    """Dozer list view."""
    dozers = Dozer.objects.all()
    grinders = Grinder.objects.filter(is_active=True)

    return render(request, 'barista/equipment/dozers.html', {
        'dozers': dozers,
        'grinders': grinders,
    })


@login_required
def tone_machine(request):
    """Tone machine configuration."""
    buttons = ToneMachineButton.objects.all()
    recipes = Recipe.objects.filter(is_active=True)

    # Ensure all 4 buttons exist
    for i in range(1, 5):
        ToneMachineButton.objects.get_or_create(button_number=i)

    buttons = ToneMachineButton.objects.all()

    return render(request, 'barista/equipment/tone_machine.html', {
        'buttons': buttons,
        'recipes': recipes,
    })


@login_required
def inventory_dashboard(request):
    """Inventory dashboard."""
    beans = Inventory.objects.filter(item_type='bean')
    cups_takeaway = Inventory.objects.filter(item_type='cup_takeaway').first()
    cups_dinein = Inventory.objects.filter(item_type='cup_dinein').first()
    servers = Inventory.objects.filter(item_type='server').first()

    return render(request, 'barista/inventory/dashboard.html', {
        'beans': beans,
        'cups_takeaway': cups_takeaway,
        'cups_dinein': cups_dinein,
        'servers': servers,
    })


@login_required
def inventory_update(request):
    """Inventory update form."""
    inventory_items = Inventory.objects.all()

    return render(request, 'barista/inventory/update.html', {
        'inventory_items': inventory_items,
    })


@login_required
def inventory_warnings(request):
    """Inventory warning thresholds configuration."""
    inventory_items = Inventory.objects.all()

    return render(request, 'barista/inventory/warnings.html', {
        'inventory_items': inventory_items,
    })


@login_required
def manual_order(request):
    """Manual order screen."""
    if not request.user.can_send_manual_orders():
        messages.error(request, 'You do not have permission to send manual orders')
        return redirect('dashboard')

    robot_connected, robot_status = check_robot_connection()
    recent_orders = ManualOrder.objects.filter(created_by=request.user)[:10]

    return render(request, 'barista/manual_order.html', {
        'robot_connected': robot_connected,
        'robot_status': robot_status,
        'recent_orders': recent_orders,
    })


@login_required
def configurations_list(request):
    """Configuration list and save."""
    configurations = SystemConfiguration.objects.all()

    return render(request, 'barista/configurations/list.html', {
        'configurations': configurations,
    })


@login_required
def settings_display(request):
    """Display settings."""
    settings = SystemSettings.get_settings()

    return render(request, 'barista/settings/display.html', {
        'settings': settings,
    })


@login_required
def settings_users(request):
    """User management (manager only)."""
    if not request.user.can_manage_users():
        messages.error(request, 'You do not have permission to manage users')
        return redirect('dashboard')

    users = UserProfile.objects.all()

    return render(request, 'barista/settings/users.html', {
        'users': users,
    })


@login_required
def settings_system(request):
    """System information."""
    from django.conf import settings as django_settings

    system_settings = SystemSettings.get_settings()

    # Get robot connection settings
    serial_port = getattr(django_settings, 'ROBOT_SERIAL_PORT', 'COM7')
    baud_rate = getattr(django_settings, 'ROBOT_BAUDRATE', 115200)
    demo_mode = getattr(django_settings, 'ROBOT_DEMO_MODE', False)

    return render(request, 'barista/settings/system.html', {
        'settings': system_settings,
        'serial_port': serial_port,
        'baud_rate': baud_rate,
        'demo_mode': demo_mode,
    })


@login_required
def analytics_overview(request):
    """Analytics overview."""
    today = timezone.now().date()
    today_orders = ManualOrder.objects.filter(
        created_at__date=today,
        status='ack'
    ).count()

    return render(request, 'barista/analytics/overview.html', {
        'today_cups': today_orders,
    })


@login_required
def analytics_reports(request):
    """Analytics reports."""
    return render(request, 'barista/analytics/reports.html')
