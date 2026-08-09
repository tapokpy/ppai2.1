from fastapi import APIRouter

from app.api.v1.endpoints import auth, chat

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(chat.router)
