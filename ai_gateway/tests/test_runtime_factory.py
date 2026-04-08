from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import load_mcp_settings
from services.mcp.runtime import ChatRuntimeFactory, NormalChatRuntime, TestModeChatRuntime


def test_runtime_factory_creates_test_mode_runtime_without_event_policy_attribute_error():
    settings = load_mcp_settings(
        {
            "mcp": {
                "host": {
                    "test_mode": True,
                    "test_mode_verbose_json": False,
                },
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    }
                },
            }
        }
    )

    runtime = ChatRuntimeFactory(request=SimpleNamespace(), mcp_settings=settings).create()

    assert isinstance(runtime, TestModeChatRuntime)


def test_runtime_factory_keeps_normal_mode_path_unchanged():
    settings = load_mcp_settings(
        {
            "mcp": {
                "host": {
                    "test_mode": False,
                },
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    }
                },
            }
        }
    )

    runtime = ChatRuntimeFactory(request=SimpleNamespace(), mcp_settings=settings).create()

    assert isinstance(runtime, NormalChatRuntime)
