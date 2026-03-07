import multiprocessing

import uvicorn as uvicorn
from uvicorn import Config

from app.core.config import settings
from app.factory import wsapp as app


WsServer = uvicorn.Server(Config(app,host=settings.HOST, port=settings.WS_PORT,
                               reload=settings.DEV, workers=multiprocessing.cpu_count(),
                               timeout_graceful_shutdown=5,loop="asyncio"))

if __name__ == '__main__':
    WsServer.run()