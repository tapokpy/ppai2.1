from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger
from sqlalchemy import text

from app.core.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="ppai", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    db_ok = True
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning(f"Health check DB failure: {exc}")
        db_ok = False

    return {"status": "ok" if db_ok else "degraded", "database": db_ok}
