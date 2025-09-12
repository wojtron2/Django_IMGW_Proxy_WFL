from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Warning

@api_view(["GET"])
def warnings_for_point(request):
    items = Warning.objects.filter(is_active=True).order_by("valid_to")
    data = [w.raw for w in items]
    return Response({"count": len(data), "warnings": data})
    
@api_view(["GET"])
def status(request):
    return Response({"status": "ok"})

