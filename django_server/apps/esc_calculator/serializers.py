from rest_framework import serializers
from .models import EscProject


class EscProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = EscProject
        fields = ['id', 'name', 'input_data', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
