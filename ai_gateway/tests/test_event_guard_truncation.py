from dataclasses import replace
from ai_gateway.services.mcp.event_guard import SystemEventGuard
from ai_gateway.services.mcp.config import McpEventPolicy
from ai_gateway.services.mcp.event_schema import SystemEvent

def test_truncation():
    policy = McpEventPolicy(
        raw_bytes_limit=100,
        verbose_json=True,
        redact_headers=True,
        max_payload_chars=4000,
        persist_system_logs=True,
        visible_band_limit=20
    )
    guard = SystemEventGuard(policy, request_id="test")
    
    # Send a large payload that will be truncated
    large_payload = {"data": "x" * 200}
    event = SystemEvent(
        kind="system_log",
        level="info",
        channel="mcp_test",
        phase="log_guard",
        title="test",
        content="test",
        request_id="test",
        provider="test",
        provider_id="test",
        provider_display_name="test",
        tool="test",
        meta={},
        fingerprint="test",
        suppressed_count=0,
        timestamp="2024-01-01T00:00:00Z"
    )
    event = replace(event, raw=large_payload)
    
    guarded = guard._apply_raw_budget(event)
    
    assert guarded.meta.get("rawTruncated") is True
    assert guarded.meta.get("rawOriginalBytes") > 100
    assert guarded.meta.get("rawTruncatedBytes") > 0
    assert guarded.meta.get("rawSuppressed") is None
    
    assert isinstance(guarded.raw, dict)
    assert guarded.raw.get("_truncated") is True
    assert "preview" in guarded.raw
    
    # Now remaining budget should be small, next large payload should be suppressed
    event2 = replace(event, raw={"data": "y" * 200})
    guarded2 = guard._apply_raw_budget(event2)
    
    assert guarded2.meta.get("rawSuppressed") is True
    assert guarded2.raw is None

