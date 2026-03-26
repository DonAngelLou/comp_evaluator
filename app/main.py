from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.grok import GrokAnalyzer
from app.adapters.news import NewsResearcher
from app.adapters.sec import SecResearcher
from app.adapters.website import WebsiteResearcher
from app.config import Settings, get_settings
from app.models import EvaluationRequest, EvaluationResponse
from app.services.evaluation import EvaluationService

BASE_DIR = Path(__file__).resolve().parent


def build_service(settings: Settings, http_client: httpx.AsyncClient) -> EvaluationService:
    return EvaluationService(
        settings=settings,
        website_researcher=WebsiteResearcher(http_client),
        sec_researcher=SecResearcher(http_client, settings),
        news_researcher=NewsResearcher(http_client, settings),
        grok_analyzer=GrokAnalyzer(settings),
    )


def create_app(settings: Settings | None = None, service: EvaluationService | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is not None:
            app.state.evaluation_service = service
            yield
            return
        async with httpx.AsyncClient(
            timeout=app_settings.request_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": app_settings.sec_user_agent},
        ) as http_client:
            app.state.http_client = http_client
            app.state.evaluation_service = build_service(app_settings, http_client)
            yield

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    if service is not None:
        app.state.evaluation_service = service
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(BASE_DIR / "templates" / "index.html")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/evaluations", response_model=EvaluationResponse)
    async def evaluate(request_body: EvaluationRequest, request: Request) -> EvaluationResponse:
        evaluation_service = getattr(request.app.state, "evaluation_service", None)
        if evaluation_service is None:
            http_client = getattr(request.app.state, "http_client", None)
            if http_client is None:
                http_client = httpx.AsyncClient(
                    timeout=app_settings.request_timeout_seconds,
                    follow_redirects=True,
                    headers={"User-Agent": app_settings.sec_user_agent},
                )
                request.app.state.http_client = http_client
            evaluation_service = build_service(app_settings, http_client)
            request.app.state.evaluation_service = evaluation_service
        try:
            return await evaluation_service.evaluate(request_body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()
