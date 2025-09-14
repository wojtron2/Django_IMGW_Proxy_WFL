from django.urls import path
from .views import warnings_for_point, status

urlpatterns = [
    path("warnings", warnings_for_point),
    path("status", status),
]