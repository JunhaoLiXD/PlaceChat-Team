"""All /api/v1 routes. Each module owner adds their router here with api_router.include_router()."""

from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")
