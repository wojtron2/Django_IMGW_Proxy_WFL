from rest_framework import serializers
from .models import Warning

class WarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warning
        fields = [
            "id","event_name","level","probability",
            "valid_from","valid_to","published_at",
            "content","comment","office"
        ]