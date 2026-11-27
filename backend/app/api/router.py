"""All /api/v1 routes. Each module owner adds their router here with api_router.include_router()."""

from fastapi import APIRouter

from app.api.admin_blocked_words import router as admin_blocked_words_router
from app.api.admin_blocks import router as admin_blocks_router
from app.api.admin_rooms import router as admin_rooms_router
from app.api.messages import router as messages_router
from app.api.reports import admin_router as admin_reports_router
from app.api.reports import router as reports_router
from app.api.rooms import router as rooms_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(rooms_router)
api_router.include_router(messages_router)
api_router.include_router(reports_router)
api_router.include_router(admin_reports_router)
api_router.include_router(admin_rooms_router)
api_router.include_router(admin_blocked_words_router)
api_router.include_router(admin_blocks_router)
