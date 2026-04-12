"""Aggregate all API routers for clean import in main.py."""

from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator
from app.api.routers.users import router as users_router
from app.api.routers.verification import router as verification_router
from app.api.routers.models import router as models_router
from app.api.routers.system import router as system_router
from app.api.routers.sensor import router as sensor_router

__all__ = [
    "users_router",
    "verification_router",
    "models_router",
    "system_router",
    "sensor_router",
]
