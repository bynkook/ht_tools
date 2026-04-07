"""
Runtime contract helpers for FabriX Chat mode consumers.
"""

from .config import McpSettings


def build_chat_runtime_contract(mcp_settings: McpSettings) -> dict:
    test_mode_enabled = mcp_settings.host.test_mode
    return {
        "mode": "mcp_test" if test_mode_enabled else "normal",
        "requires_model_selection": not test_mode_enabled,
        "supports_external_llm": not test_mode_enabled,
    }


__all__ = ["build_chat_runtime_contract"]
