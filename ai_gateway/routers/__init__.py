"""
FastAPI Routers Package
"""
from .health import router as health_router
from .agent_chat import router as agent_chat_router
from .chat import router as chat_router
from .image import router as image_router
from .doc_search import router as doc_search_router

__all__ = ["health_router", "agent_chat_router", "chat_router", "image_router", "doc_search_router"]
