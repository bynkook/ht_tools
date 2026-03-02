from rest_framework import serializers
from .models import DataExplorerPreset


class DataExplorerPresetListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing presets (minimal info).
    """
    owner_username = serializers.CharField(source='user.username', read_only=True)
    is_owner = serializers.SerializerMethodField()
    
    class Meta:
        model = DataExplorerPreset
        fields = ['id', 'name', 'description', 'is_public', 'owner_username', 'is_owner', 'created_at', 'updated_at']
        read_only_fields = ['id', 'is_public', 'owner_username', 'is_owner', 'created_at', 'updated_at']
    
    def get_is_owner(self, obj):
        """Returns True if the current user is the owner."""
        request = self.context.get('request')
        if request and request.user:
            return obj.user_id == request.user.id
        return False


class DataExplorerPresetDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for full preset details (create/read/update).
    """
    data_config = serializers.JSONField()
    chart_spec = serializers.JSONField()
    fields_meta = serializers.JSONField()
    owner_username = serializers.CharField(source='user.username', read_only=True)
    is_owner = serializers.SerializerMethodField()
    
    class Meta:
        model = DataExplorerPreset
        fields = [
            'id', 'name', 'description',
            'data_config', 'chart_spec', 'fields_meta',
            'is_public', 'owner_username', 'is_owner',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'owner_username', 'is_owner', 'created_at', 'updated_at']
    
    def get_is_owner(self, obj):
        """Returns True if the current user is the owner."""
        request = self.context.get('request')
        if request and request.user:
            return obj.user_id == request.user.id
        return False
    
    def create(self, validated_data):
        """Create preset."""
        return DataExplorerPreset.objects.create(**validated_data)
    
    def update(self, instance, validated_data):
        """Update preset."""
        return super().update(instance, validated_data)
    
    def validate_data_config(self, value):
        """Validate data_config structure."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("data_config must be a dictionary")
        
        if 'filename' not in value:
            raise serializers.ValidationError("data_config must contain 'filename'")
        
        if 'selectedColumns' in value:
            if not isinstance(value['selectedColumns'], list):
                raise serializers.ValidationError("selectedColumns must be a list")
        
        return value
    
    def validate_chart_spec(self, value):
        """Validate chart_spec has required IChart fields."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("chart_spec must be a dictionary")
        
        # IChart required fields
        required_fields = ['visId', 'encodings', 'config', 'layout']
        missing = [f for f in required_fields if f not in value]
        if missing:
            raise serializers.ValidationError(
                f"chart_spec missing required fields: {missing}"
            )
        
        return value
    
    def validate_fields_meta(self, value):
        """Validate fields_meta is a list of field objects."""
        if not isinstance(value, list):
            raise serializers.ValidationError("fields_meta must be a list")
        
        for i, field in enumerate(value):
            if not isinstance(field, dict):
                raise serializers.ValidationError(
                    f"fields_meta[{i}] must be a dictionary"
                )
            if 'fid' not in field:
                raise serializers.ValidationError(
                    f"fields_meta[{i}] must contain 'fid'"
                )
        
        return value
