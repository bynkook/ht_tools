from rest_framework import serializers


class PeLogSheetOpsSerializer(serializers.Serializer):
    base_revision = serializers.IntegerField(min_value=0)
    ops = serializers.ListField(child=serializers.DictField(), allow_empty=True)
    snapshot = serializers.ListField(child=serializers.DictField(), required=False, allow_null=True)
    client_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')


class PeLogSheetPresenceSerializer(serializers.Serializer):
    client_id = serializers.CharField(max_length=64)
