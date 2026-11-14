from fastapi import APIRouter

from app.modules.auth.dependencies import CurrentUser
from app.modules.users.models import User
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_current_user(user: CurrentUser) -> User:
    return user
