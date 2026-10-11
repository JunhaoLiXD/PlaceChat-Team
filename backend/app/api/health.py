from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check for Render. Deliberately does not touch the database."""
    return {"status": "ok"}
