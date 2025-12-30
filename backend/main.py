"""FastAPI application entry point.

This is the main entry point for the refactored AI Presentation Agent backend.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_settings, init_directories
from api import tasks_router, slides_router, websocket_router, upload_router, agent_router


# Configure logging to output to stdout for Docker
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Set specific log levels for our modules
logging.getLogger('api.upload').setLevel(logging.INFO)
logging.getLogger('api.agent').setLevel(logging.INFO)
logging.getLogger('tools.file_tools').setLevel(logging.INFO)
logging.getLogger('config.settings').setLevel(logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    settings = get_settings()
    init_directories(settings)
    
    # Log startup info for debugging
    logger.info("=" * 60)
    logger.info("AI Presentation Agent Backend Starting")
    logger.info("=" * 60)
    logger.info(f"Workspace base: {settings.workspace_base}")
    logger.info(f"Workspace base (resolved): {settings.workspace_base.resolve()}")
    logger.info(f"Prompts dir: {settings.prompts_dir}")
    logger.info(f"Prompts dir (resolved): {settings.prompts_dir.resolve()}")
    logger.info(f"Current working directory: {Path.cwd()}")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown
    logger.info("AI Presentation Agent Backend Shutting Down")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title="AI Presentation Agent",
        description="AI-powered presentation generation system",
        version="2.0.0",
        lifespan=lifespan,
        debug=settings.debug
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(tasks_router)
    app.include_router(slides_router)
    app.include_router(websocket_router)
    app.include_router(upload_router)
    app.include_router(agent_router)
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": "2.0.0"}
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "name": "AI Presentation Agent",
            "version": "2.0.0",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )