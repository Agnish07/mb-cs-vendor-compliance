from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from app.config import get_settings
from app.database import init_db
from app.routers import compliance, health
from app.services.email_monitor import email_polling_loop


settings = get_settings()

app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    if settings.email_polling_enabled:
        asyncio.create_task(email_polling_loop())


app.include_router(health.router)
app.include_router(compliance.router)
