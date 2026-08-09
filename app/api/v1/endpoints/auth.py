import secrets
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.sqlalchemy.user import User
from app.schemas.auth import GenerateOTTRequest, GenerateOTTResponse, SSORequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

OTT_KEY_PREFIX = "ott:"


async def get_redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


def verify_internal_token(x_internal_token: str = Header(...)) -> None:
    if x_internal_token != settings.INTERNAL_API_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")


@router.post(
    "/generate_ott",
    response_model=GenerateOTTResponse,
    dependencies=[Depends(verify_internal_token)],
)
async def generate_ott(
    payload: GenerateOTTRequest, redis_client: Redis = Depends(get_redis_client)
) -> GenerateOTTResponse:
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == payload.telegram_id))
        user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    token = secrets.token_urlsafe(32)
    await redis_client.set(f"{OTT_KEY_PREFIX}{token}", str(user.id), ex=settings.OTT_EXPIRES_SECONDS)

    return GenerateOTTResponse(ott=token, expires_in=settings.OTT_EXPIRES_SECONDS)


@router.post("/sso", response_model=TokenResponse)
async def sso(payload: SSORequest, redis_client: Redis = Depends(get_redis_client)) -> TokenResponse:
    key = f"{OTT_KEY_PREFIX}{payload.ott}"
    user_id_raw = await redis_client.get(key)

    if user_id_raw is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    await redis_client.delete(key)

    access_token = create_access_token(int(user_id_raw))

    return TokenResponse(access_token=access_token, expires_in=settings.JWT_EXPIRES_HOURS * 3600)
