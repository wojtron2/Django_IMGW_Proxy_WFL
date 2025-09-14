from django.urls import path
from . import views

urlpatterns = [
    path("warnings", views.warnings_for_point, name="warnings-for-point"),
    path("status", views.status, name="status"),
    path("health", views.status, name="health"),
]