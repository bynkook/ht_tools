"""
MCP service package for generic host migration work.
"""

from .config import (
    McpHostSettings,
    McpEventPolicy,
    McpServerConfig,
    McpSettings,
    build_mcp_event_policy,
    load_doc_search_server_config,
    load_mcp_host_settings,
    load_mcp_settings,
)
from .context_merge import build_multi_file_system_prompt, merge_system_prompts
from .event_emitter import SystemEventEmitter
from .event_guard import SystemEventGuard
from .event_schema import SystemEvent, build_event_fingerprint
from .host import (
    GenericMcpHost,
    McpChatResolution,
    build_context_debug_payload,
    normalize_context_result,
)
from .intent_router import (
    IntentRouteDecision,
    parse_at_mentions,
    route_chat_query,
    split_mention_target,
    strip_at_mentions,
)
from .providers import InternalDocsProvider
from .rag_context import build_rag_response
from .registry import connect_provider, get_provider_config, list_provider_configs
from .result_normalizer import tool_result_to_dict, tool_result_to_text
from .runtime_contract import build_chat_runtime_contract
from .test_mode import DeterministicToolPlanner, ProtocolRecorder, ScenarioLoader, ToolDecisionProvenance, ToolPlan

__all__ = [
    "build_multi_file_system_prompt",
    "build_mcp_event_policy",
    "build_rag_response",
    "connect_provider",
    "DeterministicToolPlanner",
    "GenericMcpHost",
    "get_provider_config",
    "build_event_fingerprint",
    "build_chat_runtime_contract",
    "build_context_debug_payload",
    "McpEventPolicy",
    "McpHostSettings",
    "InternalDocsProvider",
    "IntentRouteDecision",
    "list_provider_configs",
    "McpChatResolution",
    "McpServerConfig",
    "McpSettings",
    "SystemEvent",
    "SystemEventEmitter",
    "SystemEventGuard",
    "ToolDecisionProvenance",
    "load_doc_search_server_config",
    "load_mcp_host_settings",
    "load_mcp_settings",
    "merge_system_prompts",
    "normalize_context_result",
    "parse_at_mentions",
    "ProtocolRecorder",
    "route_chat_query",
    "split_mention_target",
    "strip_at_mentions",
    "ScenarioLoader",
    "ToolPlan",
    "tool_result_to_dict",
    "tool_result_to_text",
]
