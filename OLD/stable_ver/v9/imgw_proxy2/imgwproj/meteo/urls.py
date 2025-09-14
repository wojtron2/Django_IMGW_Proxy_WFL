from django.urls import path
from .views import (
    warnings_for_point,
    status_view,         
    warnings_for_teryt,
    history_for_point,
    history_for_teryt,
    warnings_live,
)

urlpatterns = [
    path("warnings", warnings_for_point),
    path("warnings/teryt/<str:teryt4>", warnings_for_teryt),
    path("warnings/live", warnings_live),
    path("history", history_for_point),
    path("history/teryt/<str:teryt4>", history_for_teryt),
    path("status", status_view),
]
