import os
from dataclasses import dataclass


@dataclass
class Settings:
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    database_url: str = os.getenv("DATABASE_URL", "app.db")
    token_ttl: int = int(os.getenv("TOKEN_TTL", "3600"))


settings = Settings()
