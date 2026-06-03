from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/publication_db"
    SECRET_KEY: str = "changeme-use-a-long-random-string-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "publication_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""

    DEFAULT_ORG_NAME: str = "ФИЦ ИВТ"
    DEFAULT_ORG_ID: int = 1

    class Config:
        env_file = ".env"


settings = Settings()
