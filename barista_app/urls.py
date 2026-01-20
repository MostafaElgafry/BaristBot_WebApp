"""
URL configuration for Barista Robot Control System HTML pages.
"""
from django.urls import path
from . import views

urlpatterns = [
    # Entry screens
    path('', views.barista_display, name='barista-display'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Equipment
    path('equipment/', views.equipment_overview, name='equipment-overview'),
    path('equipment/grinders/', views.grinders_list, name='grinders-list'),
    path('equipment/dozers/', views.dozers_list, name='dozers-list'),
    path('equipment/tone-machine/', views.tone_machine, name='tone-machine'),

    # Inventory
    path('inventory/', views.inventory_dashboard, name='inventory-dashboard'),
    path('inventory/update/', views.inventory_update, name='inventory-update'),
    path('inventory/warnings/', views.inventory_warnings, name='inventory-warnings'),

    # Manual Order
    path('manual-order/', views.manual_order, name='manual-order'),

    # Configurations
    path('configurations/', views.configurations_list, name='configurations-list'),

    # Settings
    path('settings/', views.settings_display, name='settings-display'),
    path('settings/users/', views.settings_users, name='settings-users'),
    path('settings/system/', views.settings_system, name='settings-system'),

    # Analytics
    path('analytics/', views.analytics_overview, name='analytics-overview'),
    path('analytics/reports/', views.analytics_reports, name='analytics-reports'),
]
