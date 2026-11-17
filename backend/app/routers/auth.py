from fastapi import APIRouter, Depends

from ..deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user
