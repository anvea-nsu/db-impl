from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.database import engine
from app.routers import auth, organizations, journals, authors, articles, statistics, import_, admin
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("pubapp")

# SQL to create app_users if missing (safe with IF NOT EXISTS)
CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS app_users (
    id               SERIAL       PRIMARY KEY,
    username         VARCHAR(100) NOT NULL UNIQUE,
    email            VARCHAR(320) NOT NULL UNIQUE,
    hashed_password  VARCHAR(200) NOT NULL,
    role             VARCHAR(20)  NOT NULL DEFAULT 'user'
                         CHECK (role IN ('admin', 'user')),
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE
);
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create app_users table if it doesn't exist yet, then start."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text(CREATE_USERS_SQL))
        log.info("app_users table ready")
    except Exception as e:
        log.error(f"Failed to create app_users table: {e}")
    yield
    await engine.dispose()


app = FastAPI(
    title="Scientific Publications API",
    description="API для управления и анализа научных публикаций",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # dev: allow all; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(journals.router)
app.include_router(authors.router)
app.include_router(articles.router)
app.include_router(statistics.router)
app.include_router(import_.router)
app.include_router(admin.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.exception(f"Unhandled error on {request.method} {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


@app.get("/")
async def root():
    return {"status": "ok", "docs": "/docs"}
