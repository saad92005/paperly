from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUserDep
from app.db import get_session
from app.schemas.me import Profile, ProfileUpdate
from app.services import profiles

router = APIRouter(prefix="/v1", tags=["me"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/me")
async def get_me(user: CurrentUserDep, session: SessionDep) -> Profile:
    return await profiles.get_me(session, user)


@router.patch("/me")
async def patch_me(body: ProfileUpdate, user: CurrentUserDep, session: SessionDep) -> Profile:
    return await profiles.update_me(session, user, body)
