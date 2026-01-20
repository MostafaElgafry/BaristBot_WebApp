"""
URL configuration for barista_project.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('barista_app.urls')),
    path('api/', include('barista_app.api_urls')),
]
