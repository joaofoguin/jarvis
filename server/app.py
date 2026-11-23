import secrets
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from server.config import Settings, get_settings
from server.database import Base, build_database
from server.models import Task
from server.schemas import ChatRequest, ChatResponse, TaskResponse
from server.service import process_chat
from server.deepseek import DeepSeekError

def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    engine, session_factory = build_database(app_settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if engine is not None and app_settings.auto_create_schema:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title=app_settings.app_name, version="2.0.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.session_factory = session_factory

    async def get_session(request: Request):
        factory = request.app.state.session_factory
        if factory is None:
            raise HTTPException(status_code=503, detail="Banco de dados não configurado.")
        async with factory() as session:
            yield session

    def require_token(request: Request, authorization: str | None = Header(default=None)):
        expected = request.app.state.settings.jarvis_api_token
        if not expected:
            raise HTTPException(status_code=503, detail="JARVIS_API_TOKEN não configurado.")
        if not secrets.compare_digest(authorization or "", "Bearer " + expected):
            raise HTTPException(status_code=401, detail="Token de acesso inválido.")
        return True

    @app.get("/health/live")
    async def health_live():
        return {"status": "alive", "service": "jarvis"}

    @app.get("/health/ready")
    async def health_ready():
        if engine is None:
            raise HTTPException(status_code=503, detail="Banco de dados não configurado.")
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as error:
            raise HTTPException(status_code=503, detail="Banco de dados indisponível.") from error
        return {"status": "ready", "database": "connected"}

    @app.post("/api/v1/chat", response_model=ChatResponse, dependencies=[Depends(require_token)])
    async def chat(request: ChatRequest, session: AsyncSession = Depends(get_session)):
        try:
            return await process_chat(request, session, app_settings)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except DeepSeekError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/v1/tasks", response_model=list[TaskResponse], dependencies=[Depends(require_token)])
    async def list_tasks(session: AsyncSession = Depends(get_session)):
        result = await session.execute(select(Task).order_by(Task.created_at.desc()).limit(100))
        return [TaskResponse(id=item.id, title=item.title, description=item.description, status=item.status, created_at=item.created_at.isoformat()) for item in result.scalars().all()]

    return app
