from fastapi import FastAPI,APIRouter

from app.core.config import settings

api_router = APIRouter()
def init_websocket_routers(app: FastAPI):
    from app.websocket.websocket import router
    app.include_router(router, prefix=settings.WS_V1_STR)