"""
MCP service package for generic host migration work.
"""

from .config import McpServerConfig, load_doc_search_server_config
from .context_merge import build_multi_file_system_prompt, merge_system_prompts
from .host import GenericMcpHost, McpChatResolution
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

__all__ = [
    "build_multi_file_system_prompt",
    "build_rag_response",
    "connect_provider",
    "GenericMcpHost",
    "get_provider_config",
    "InternalDocsProvider",
    "IntentRouteDecision",
    "list_provider_configs",
    "McpChatResolution",
    "McpServerConfig",
    "load_doc_search_server_config",
    "merge_system_prompts",
    "parse_at_mentions",
    "route_chat_query",
    "split_mention_target",
    "strip_at_mentions",
    "tool_result_to_dict",
    "tool_result_to_text",
]
