"""
DRF Serializers for Barista Robot Control System.
"""
from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import (
    UserProfile, CoffeeType, Grinder, Dozer, Recipe,
    ToneMachineButton, Inventory, ManualOrder, SystemConfiguration,
    SystemSettings, ActivityLog, AnalyticsDaily
)


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profiles."""
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'role_display', 'last_activity', 'is_active',
            'date_joined', 'last_login'
        ]
        read_only_fields = ['id', 'date_joined', 'last_login', 'last_activity']


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new users."""
    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = UserProfile
        fields = ['username', 'email', 'password', 'password_confirm', 'role', 'first_name', 'last_name']

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match"})
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = UserProfile(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data['username'], password=data['password'])
        if not user:
            raise serializers.ValidationError("Invalid credentials")
        if not user.is_active:
            raise serializers.ValidationError("User account is disabled")
        data['user'] = user
        return data


class CoffeeTypeSerializer(serializers.ModelSerializer):
    """Serializer for coffee types."""

    class Meta:
        model = CoffeeType
        fields = ['id', 'name', 'description', 'origin', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class GrinderSerializer(serializers.ModelSerializer):
    """Serializer for grinder configuration."""
    coffee_type_name = serializers.CharField(source='coffee_type.name', read_only=True)

    class Meta:
        model = Grinder
        fields = [
            'id', 'name', 'coffee_type', 'coffee_type_name',
            'grind_level', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DozerSerializer(serializers.ModelSerializer):
    """Serializer for dozer configuration."""
    linked_grinder_name = serializers.CharField(source='linked_grinder.name', read_only=True)

    class Meta:
        model = Dozer
        fields = [
            'id', 'name', 'dose_grams', 'linked_grinder',
            'linked_grinder_name', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RecipeSerializer(serializers.ModelSerializer):
    """Serializer for recipes."""

    class Meta:
        model = Recipe
        fields = [
            'id', 'name', 'description', 'dose_grams', 'grind_grade',
            'doser_number', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ToneMachineButtonSerializer(serializers.ModelSerializer):
    """Serializer for tone machine buttons."""
    recipe_name = serializers.CharField(source='recipe.name', read_only=True)

    class Meta:
        model = ToneMachineButton
        fields = [
            'id', 'button_number', 'recipe', 'recipe_name',
            'label', 'is_active', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']


class InventorySerializer(serializers.ModelSerializer):
    """Serializer for inventory items."""
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)
    coffee_type_name = serializers.CharField(source='coffee_type.name', read_only=True)
    is_warning = serializers.BooleanField(read_only=True)

    class Meta:
        model = Inventory
        fields = [
            'id', 'item_type', 'item_type_display', 'name',
            'current_level', 'current_count', 'warning_threshold',
            'coffee_type', 'coffee_type_name', 'is_warning', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at', 'is_warning']


class ManualOrderSerializer(serializers.ModelSerializer):
    """Serializer for manual orders."""
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ManualOrder
        fields = [
            'id', 'dose_grams', 'grind_grade', 'doser_number', 'recipe_number',
            'status', 'status_display', 'response_message',
            'created_by', 'created_by_username', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'response_message', 'created_by', 'created_at']

    def validate_dose_grams(self, value):
        if not 1 <= value <= 200:
            raise serializers.ValidationError("Dose must be between 1 and 200 grams")
        return int(value)

    def validate_grind_grade(self, value):
        if not 1 <= value <= 11:
            raise serializers.ValidationError("Grind grade must be between 1 and 11")
        return value

    def validate_doser_number(self, value):
        if not 1 <= value <= 4:
            raise serializers.ValidationError("Doser number must be between 1 and 4")
        return value

    def validate_recipe_number(self, value):
        if not 1 <= value <= 4:
            raise serializers.ValidationError("Recipe number must be between 1 and 4")
        return value


class SystemConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for system configurations."""
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = SystemConfiguration
        fields = [
            'id', 'name', 'description', 'config_data',
            'include_grinders', 'include_dozers', 'include_tone_machine',
            'include_inventory_thresholds', 'include_display_preferences',
            'created_by', 'created_by_username', 'created_at'
        ]
        read_only_fields = ['id', 'config_data', 'created_by', 'created_at']


class SystemSettingsSerializer(serializers.ModelSerializer):
    """Serializer for system settings."""
    theme_display = serializers.CharField(source='get_theme_display', read_only=True)
    language_display = serializers.CharField(source='get_language_display', read_only=True)

    class Meta:
        model = SystemSettings
        fields = [
            'id', 'theme', 'theme_display', 'brightness', 'volume',
            'language', 'language_display', 'screen_timeout_minutes',
            'robot_version', 'firmware_version', 'ip_address',
            'last_sync', 'updated_at'
        ]
        read_only_fields = ['id', 'robot_version', 'firmware_version', 'updated_at']


class ActivityLogSerializer(serializers.ModelSerializer):
    """Serializer for activity logs."""
    action_type_display = serializers.CharField(source='get_action_type_display', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = ActivityLog
        fields = [
            'id', 'action_type', 'action_type_display',
            'description', 'user', 'username', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AnalyticsDailySerializer(serializers.ModelSerializer):
    """Serializer for daily analytics."""

    class Meta:
        model = AnalyticsDaily
        fields = [
            'id', 'date', 'total_cups', 'cups_per_hour',
            'recipe_distribution', 'bean_usage', 'peak_hour',
            'top_recipe', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MachineOrderInputSerializer(serializers.Serializer):
    """Serializer for incoming machine API orders. Only requires order_name + order_id."""
    order_name = serializers.CharField(
        max_length=100,
        help_text="Recipe name (must match an active Recipe)"
    )
    order_id = serializers.CharField(
        max_length=100,
        help_text="External order ID from the calling system"
    )

    def validate_order_name(self, value):
        from .models import Recipe
        try:
            recipe = Recipe.objects.get(name__iexact=value, is_active=True)
        except Recipe.DoesNotExist:
            active_recipes = list(
                Recipe.objects.filter(is_active=True).values_list('name', flat=True)
            )
            raise serializers.ValidationError(
                f"No active recipe found with name '{value}'. "
                f"Available recipes: {active_recipes}"
            )
        return value


class MachineOrderResponseSerializer(serializers.ModelSerializer):
    """Serializer for machine API order responses."""
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ManualOrder
        fields = [
            'id', 'external_order_id', 'order_name',
            'dose_grams', 'grind_grade', 'doser_number', 'recipe_number',
            'status', 'status_display', 'source', 'response_message', 'created_at'
        ]


class DashboardSerializer(serializers.Serializer):
    """Serializer for dashboard data."""
    user = UserProfileSerializer(read_only=True)
    system_status = serializers.DictField(read_only=True)
    warnings = serializers.ListField(read_only=True)
    recent_activity = ActivityLogSerializer(many=True, read_only=True)
    robot_connected = serializers.BooleanField(read_only=True)
