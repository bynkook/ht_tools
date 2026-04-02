from rest_framework import serializers

from .models import ConversionJob


class ConversionJobSerializer(serializers.ModelSerializer):
    """공개 API 응답용 — callback_token 제외"""

    class Meta:
        model = ConversionJob
        fields = [
            'id',
            'original_filename',
            'category_name',
            'status',
            'error_message',
            'created_at',
        ]
        read_only_fields = fields


class ConversionJobCreateSerializer(serializers.ModelSerializer):
    """내부 생성용 — callback_token 포함"""

    class Meta:
        model = ConversionJob
        fields = [
            'id',
            'original_filename',
            'category_name',
            'status',
            'callback_token',
        ]
        read_only_fields = ['id', 'callback_token']
