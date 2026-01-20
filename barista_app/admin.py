"""
Django Admin configuration for Barista Robot Control System.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    UserProfile, CoffeeType, Grinder, Dozer, Recipe,
    ToneMachineButton, Inventory, ManualOrder, SystemConfiguration,
    SystemSettings, ActivityLog, AnalyticsDaily
)


@admin.register(UserProfile)
class UserProfileAdmin(UserAdmin):
    list_display = ['username', 'email', 'role', 'is_active', 'last_login']
    list_filter = ['role', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('role', 'last_activity')}),
    )


@admin.register(CoffeeType)
class CoffeeTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'origin', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'origin']


@admin.register(Grinder)
class GrinderAdmin(admin.ModelAdmin):
    list_display = ['name', 'coffee_type', 'grind_level', 'is_active']
    list_filter = ['is_active', 'coffee_type']


@admin.register(Dozer)
class DozerAdmin(admin.ModelAdmin):
    list_display = ['name', 'dose_grams', 'linked_grinder', 'is_active']
    list_filter = ['is_active', 'linked_grinder']


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_filter = ['is_active']


@admin.register(ToneMachineButton)
class ToneMachineButtonAdmin(admin.ModelAdmin):
    list_display = ['button_number', 'recipe', 'label', 'is_active']
    list_filter = ['is_active']


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'item_type', 'current_level', 'warning_threshold', 'is_warning']
    list_filter = ['item_type']


@admin.register(ManualOrder)
class ManualOrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'dose_grams', 'grind_grade', 'recipe_number', 'status', 'created_by', 'created_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['created_at']


@admin.register(SystemConfiguration)
class SystemConfigurationAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'created_at']
    readonly_fields = ['config_data', 'created_at']


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ['theme', 'language', 'brightness', 'volume']


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['action_type', 'description', 'user', 'created_at']
    list_filter = ['action_type', 'created_at']
    readonly_fields = ['created_at']


@admin.register(AnalyticsDaily)
class AnalyticsDailyAdmin(admin.ModelAdmin):
    list_display = ['date', 'total_cups', 'peak_hour', 'top_recipe']
    list_filter = ['date']
