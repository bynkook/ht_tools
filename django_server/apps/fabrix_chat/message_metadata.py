from rest_framework import serializers

SYSTEM_MESSAGE_METADATA_FIELD_TYPES = {
    'kind': str,
    'level': str,
    'channel': str,
    'title': (str, type(None)),
    'phase': (str, type(None)),
    'provider': (str, type(None)),
    'providerId': (str, type(None)),
    'providerDisplayName': (str, type(None)),
    'tool': (str, type(None)),
    'selectionReason': (str, type(None)),
    'selectionRank': (int, type(None)),
    'candidateSummary': object,
    'partialFailure': object,
    'requestId': (str, type(None)),
    'fingerprint': (str, type(None)),
    'timestamp': (str, type(None)),
    'persist': bool,
    'repeatCount': int,
    'suppressedCount': int,
    'rawSuppressed': bool,
    'rawSuppressedCount': int,
    'raw': object,
}


def validate_chat_message_metadata(role, metadata):
    if metadata is None:
        return {}

    if not isinstance(metadata, dict):
        raise serializers.ValidationError('metadata must be an object')

    if role != 'system' or not metadata:
        return metadata

    unknown_keys = sorted(set(metadata.keys()) - set(SYSTEM_MESSAGE_METADATA_FIELD_TYPES.keys()))
    if unknown_keys:
        raise serializers.ValidationError(
            f"unknown system metadata keys: {', '.join(unknown_keys)}"
        )

    for field_name, expected_type in SYSTEM_MESSAGE_METADATA_FIELD_TYPES.items():
        if field_name not in metadata:
            continue
        if expected_type is object:
            continue
        if not isinstance(metadata[field_name], expected_type):
            raise serializers.ValidationError(
                f'metadata.{field_name} has invalid type'
            )

    required_fields = ('kind', 'level', 'channel', 'phase', 'persist')
    missing_fields = [field_name for field_name in required_fields if field_name not in metadata]
    if missing_fields:
        raise serializers.ValidationError(
            f"missing system metadata keys: {', '.join(missing_fields)}"
        )

    return metadata