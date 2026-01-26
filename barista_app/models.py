"""
Django models for Barista Robot Control System.
"""
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
import json


class UserProfile(AbstractUser):
    """Extended user model with role management."""
    ROLE_CHOICES = [
        ('barista', 'Barista'),
        ('technician', 'Technician'),
        ('supervisor', 'Supervisor'),
        ('manager', 'Manager'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='barista')
    last_activity = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'user_profiles'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    def can_configure_equipment(self):
        return self.role in ['technician', 'manager']

    def can_manage_inventory(self):
        return self.role in ['supervisor', 'manager']

    def can_send_manual_orders(self):
        return self.role in ['supervisor', 'technician', 'manager']

    def can_manage_users(self):
        return self.role == 'manager'


class CoffeeType(models.Model):
    """Coffee bean types available."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    origin = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coffee_types'
        ordering = ['name']

    def __str__(self):
        return self.name


class Grinder(models.Model):
    """Grinder equipment configuration."""
    name = models.CharField(max_length=100)
    coffee_type = models.ForeignKey(
        CoffeeType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grinders'
    )
    grind_level = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        default=5,
        help_text="Grind level from 1 (fine) to 10 (coarse)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'grinders'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - Level {self.grind_level}"


class Dozer(models.Model):
    """Dozer equipment configuration."""
    name = models.CharField(max_length=100)
    dose_grams = models.FloatField(
        validators=[MinValueValidator(0.1), MaxValueValidator(200.0)],
        default=18.0,
        help_text="Dose in grams (0.1-200.0)"
    )
    linked_grinder = models.ForeignKey(
        Grinder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dozers'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dozers'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.dose_grams}g"


class Recipe(models.Model):
    """Recipe definitions for tone machine buttons."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'recipes'
        ordering = ['name']

    def __str__(self):
        return self.name


class ToneMachineButton(models.Model):
    """Tone machine button configuration (4 buttons)."""
    BUTTON_CHOICES = [(i, f'Button {i}') for i in range(1, 5)]

    button_number = models.IntegerField(
        choices=BUTTON_CHOICES,
        unique=True,
        validators=[MinValueValidator(1), MaxValueValidator(4)]
    )
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tone_buttons'
    )
    label = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tone_machine_buttons'
        ordering = ['button_number']

    def __str__(self):
        recipe_name = self.recipe.name if self.recipe else 'Unassigned'
        return f"Button {self.button_number}: {recipe_name}"


class Inventory(models.Model):
    """Inventory tracking for beans, cups, and servers."""
    ITEM_TYPES = [
        ('bean', 'Coffee Beans'),
        ('cup_takeaway', 'Takeaway Cups'),
        ('cup_dinein', 'Dine-in Cups'),
        ('server', 'Servers'),
    ]

    item_type = models.CharField(max_length=20, choices=ITEM_TYPES)
    name = models.CharField(max_length=100)
    current_level = models.FloatField(
        default=100.0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Current level as percentage (0-100)"
    )
    current_count = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Current count for cups/servers"
    )
    warning_threshold = models.FloatField(
        default=20.0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Warning threshold percentage"
    )
    coffee_type = models.ForeignKey(
        CoffeeType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_items'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory'
        verbose_name_plural = 'Inventory items'

    def __str__(self):
        return f"{self.name} ({self.get_item_type_display()})"

    @property
    def is_warning(self):
        """Check if inventory is below warning threshold."""
        return self.current_level <= self.warning_threshold


class ManualOrder(models.Model):
    """Manual orders sent to the robot."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('ack', 'Acknowledged'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('error', 'Error'),
    ]

    dose_grams = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(200)]
    )
    grind_grade = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(11)]
    )
    doser_number = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        default=1,
        help_text="Doser number (1-4)"
    )
    recipe_number = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(4)]
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    response_message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='manual_orders'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'manual_orders'
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} - {self.dose_grams}g, Grade {self.grind_grade}, Recipe {self.recipe_number}"


class SystemConfiguration(models.Model):
    """Saved system configurations for backup/restore."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    config_data = models.JSONField(default=dict)
    include_grinders = models.BooleanField(default=True)
    include_dozers = models.BooleanField(default=True)
    include_tone_machine = models.BooleanField(default=True)
    include_inventory_thresholds = models.BooleanField(default=True)
    include_display_preferences = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='configurations'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'system_configurations'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.created_at.strftime('%Y-%m-%d')})"


class SystemSettings(models.Model):
    """Global system settings (singleton)."""
    THEME_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
    ]
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('es', 'Spanish'),
        ('fr', 'French'),
    ]

    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='light')
    brightness = models.IntegerField(
        default=80,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    volume = models.IntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='en')
    screen_timeout_minutes = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(60)]
    )
    robot_version = models.CharField(max_length=20, default='v2.3.1')
    firmware_version = models.CharField(max_length=20, default='v1.8.5')
    ip_address = models.CharField(max_length=45, default='192.168.1.100')
    last_sync = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_settings'
        verbose_name_plural = 'System settings'

    def __str__(self):
        return "System Settings"

    @classmethod
    def get_settings(cls):
        """Get or create singleton settings instance."""
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings


class ActivityLog(models.Model):
    """System activity logging for analytics."""
    ACTION_TYPES = [
        ('order_sent', 'Order Sent'),
        ('order_completed', 'Order Completed'),
        ('order_failed', 'Order Failed'),
        ('config_changed', 'Configuration Changed'),
        ('inventory_updated', 'Inventory Updated'),
        ('user_login', 'User Login'),
        ('user_logout', 'User Logout'),
        ('system_warning', 'System Warning'),
    ]

    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
    description = models.TextField()
    user = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs'
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'activity_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_action_type_display()} - {self.created_at}"


class AnalyticsDaily(models.Model):
    """Daily aggregated analytics data."""
    date = models.DateField(unique=True)
    total_cups = models.IntegerField(default=0)
    cups_per_hour = models.JSONField(default=dict)  # {"08": 5, "09": 12, ...}
    recipe_distribution = models.JSONField(default=dict)  # {"1": 20, "2": 35, ...}
    bean_usage = models.JSONField(default=dict)  # {"Ethiopian": 500, ...}
    peak_hour = models.IntegerField(null=True, blank=True)
    top_recipe = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_daily'
        ordering = ['-date']
        verbose_name_plural = 'Daily analytics'

    def __str__(self):
        return f"Analytics for {self.date}"
