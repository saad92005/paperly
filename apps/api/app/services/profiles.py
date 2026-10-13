"""Profile business logic."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.repos import profiles as repo
from app.schemas.me import Profile, ProfileUpdate


async def get_me(session: AsyncSession, user: CurrentUser) -> Profile:
    row = await repo.get_or_create(session, user.id)
    return Profile(**row, email=user.email)


async def update_me(session: AsyncSession, user: CurrentUser, patch: ProfileUpdate) -> Profile:
    await repo.get_or_create(session, user.id)
    row = await repo.update(session, user.id, patch.model_dump(exclude_unset=True))
    return Profile(**row, email=user.email)
