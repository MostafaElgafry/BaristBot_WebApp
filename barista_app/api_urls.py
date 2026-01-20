"""
API URL configuration for Barista Robot Control System.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views

router = DefaultRouter()
router.register(r'users', api_views.UserViewSet, basename='user')
router.register(r'coffee-types', api_views.CoffeeTypeViewSet, basename='coffee-type')
router.register(r'grinders', api_views.GrinderViewSet, basename='grinder')
router.register(r'dozers', api_views.DozerViewSet, basename='dozer')
router.register(r'recipes', api_views.RecipeViewSet, basename='recipe')
router.register(r'tone-buttons', api_views.ToneMachineButtonViewSet, basename='tone-button')
router.register(r'inventory', api_views.InventoryViewSet, basename='inventory')
router.register(r'orders', api_views.ManualOrderViewSet, basename='order')
router.register(r'configurations', api_views.SystemConfigurationViewSet, basename='configuration')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/login/', api_views.LoginAPIView.as_view(), name='api-login'),
    path('auth/logout/', api_views.LogoutAPIView.as_view(), name='api-logout'),
    path('dashboard/', api_views.DashboardAPIView.as_view(), name='api-dashboard'),
    path('settings/', api_views.SystemSettingsAPIView.as_view(), name='api-settings'),
    path('analytics/', api_views.AnalyticsAPIView.as_view(), name='api-analytics'),
    path('robot/status/', api_views.RobotStatusAPIView.as_view(), name='api-robot-status'),
]
