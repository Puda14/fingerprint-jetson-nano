"""
Aggregate all API routers for clean import in main.py.
"""

from web.backend.routers.users import router as users_router
from web.backend.routers.verification import router as verification_router
from web.backend.routers.models import router as models_router
from web.backend.routers.system import router as system_router
from web.backend.routers.sensor import router as sensor_router

__all__ = [
    "users_router",
    "verification_router",
    "models_router",
    "system_router",
    "sensor_router",
]
