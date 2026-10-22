"""Data access for the administrator allow-list. Provisioning belongs to Junhao."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth_models import AdminUser


def is_admin_user(db: Session, user_id: UUID) -> bool:
    return db.scalar(select(AdminUser.user_id).where(AdminUser.user_id == user_id)) is not None
