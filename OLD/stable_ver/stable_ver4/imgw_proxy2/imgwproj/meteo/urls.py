from django.urls import path
from .views import warnings_for_point

urlpatterns = [
    path("warnings", warnings_for_point),
]
