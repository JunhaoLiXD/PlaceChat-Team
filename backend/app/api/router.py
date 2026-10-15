"""All /api/v1 routes. Each module owner adds their router here with api_router.include_router()."""

from fastapi import APIRouter

from app.api.admin_rooms import router as admin_rooms_router
from app.api.rooms import router as rooms_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(rooms_router)
api_router.include_router(admin_rooms_router)
