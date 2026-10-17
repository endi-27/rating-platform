import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DbSettings(BaseModel):
    user: Annotated[str, Field(description="PostgreSQL username")] = "rating_user"
    password: Annotated[str, Field(description="PostgreSQL password")] = "rating_secret_password"
    name: Annotated[str, Field(description="Database name")] = "rating_db"
    host: Annotated[str, Field(description="PostgreSQL host")] = "127.0.0.1"
    port: Annotated[int, Field(description="PostgreSQL port")] = 5432
    echo: Annotated[bool, Field(description="SQLAlchemy echo SQL queries")] = False

    pool_size: Annotated[int, Field(description="Connection pool size", ge=1, le=100)] = 10
    max_overflow: Annotated[int, Field(description="Max pool overflow connections", ge=0, le=100)] = 10
    pool_timeout: Annotated[
        float,
        Field(description="Seconds to wait before timing out on getting connection", ge=1.0),
    ] = 30.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisDBSettings(BaseModel):
    cache: Annotated[int, Field(description="Redis DB index for caching", ge=0, le=15)] = 0
    task: Annotated[int, Field(description="Redis DB index for ARQ background tasks", ge=0, le=15)] = 1


class RedisSettings(BaseModel):
    host: Annotated[str, Field(description="Redis host")] = "127.0.0.1"
    port: Annotated[int, Field(description="Redis port")] = 6379
    password: Annotated[str | None, Field(description="Redis password")] = None
    databases: RedisDBSettings = RedisDBSettings()

    def get_url(self, db: int | None = None) -> str:
        """Генерує URL підключення до Redis для вказаного індексу бази даних."""
        target_db = db if db is not None else self.databases.cache
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{target_db}"
        return f"redis://{self.host}:{self.port}/{target_db}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        """Базовий URL підключення (за замовчуванням база кешування)."""
        return self.get_url(self.databases.cache)


class AuthSettings(BaseModel):
    access_secret_key: Annotated[str, Field(description="JWT signing secret key", min_length=32)] = (
        "local-dev-secret-key-min-32-chars-for-rating-platform"
    )
    algorithm: Annotated[str, Field(description="JWT algorithm")] = "HS256"
    access_token_expire_minutes: Annotated[int, Field(description="Access token TTL in minutes", ge=1)] = 15
    refresh_token_expire_days: Annotated[int, Field(description="Refresh token TTL in days", ge=1)] = 1
    refresh_token_remember_me_expire_days: Annotated[
        int, Field(description="Remember me refresh token TTL in days", ge=1)
    ] = 7
    max_session_expiration_days: Annotated[int, Field(description="Maximum session lifespan in days", ge=1)] = 30
    bcrypt_rounds: Annotated[int, Field(description="Bcrypt hashing rounds (cost factor)", ge=4, le=31)] = 12


class ApiSettings(BaseModel):
    v1_prefix: Annotated[str, Field(description="API v1 URL prefix")] = "/api/v1"
    cors_origins: Annotated[list[str], Field(description="Allowed CORS origins")] = [
        "http://localhost",
        "https://localhost",
        "http://127.0.0.1",
        "http://localhost:3000",
        "https://localhost:3000",
        "http://localhost:5173",
        "https://localhost:5173",
        "http://127.0.0.1:3000",
        "https://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "https://127.0.0.1:5173",
    ]


class ArqSettings(BaseModel):
    max_jobs: Annotated[int, Field(description="Max concurrent jobs in ARQ worker", ge=1, le=100)] = 10
    job_timeout: Annotated[int, Field(description="Job execution timeout in seconds", ge=1)] = 300
    max_tries: Annotated[int, Field(description="Max retry attempts for failed jobs", ge=1)] = 3
    keep_result: Annotated[int, Field(description="Duration to keep job result in Redis in seconds", ge=0)] = 3600
    health_check_interval: Annotated[int, Field(description="Healthcheck interval in seconds", ge=1)] = 30
    queue_name: Annotated[str, Field(description="Redis queue name for ARQ")] = "arq:queue"


class CacheNamespaceSettings(BaseModel):
    users: Annotated[str, Field(description="Namespace for users")] = "users"
    roles: Annotated[str, Field(description="Namespace for roles")] = "roles"
    permissions: Annotated[str, Field(description="Namespace for permissions")] = "permissions"
    targets: Annotated[str, Field(description="Namespace for targets")] = "targets"
    reviews: Annotated[str, Field(description="Namespace for reviews")] = "reviews"


class CacheSettings(BaseModel):
    prefix: Annotated[str, Field(description="Redis cache key prefix")] = "rating_cache"
    expire: Annotated[int, Field(description="Default cache TTL in seconds", ge=1)] = 60
    targets_expire: Annotated[int, Field(description="Target details cache TTL in seconds", ge=1)] = 60
    reviews_expire: Annotated[int, Field(description="Reviews and ratings cache TTL in seconds", ge=1)] = 30
    namespace: CacheNamespaceSettings = CacheNamespaceSettings()


class RedisSetSettings(BaseModel):
    prefix: Annotated[str, Field(description="Redis Set key prefix")] = "rating_set"
    dirty_targets: Annotated[str, Field(description="Redis Set key for targets awaiting rating recalculation")] = (
        "ratings:dirty_targets"
    )

    @property
    def dirty_targets_key(self) -> str:
        """Повний складений ключ для черги перерахунку рейтингів."""
        return f"{self.prefix}:{self.dirty_targets}"


class LogSettings(BaseModel):
    dir: Annotated[Path, Field(description="Logs root directory")] = Path("logs")
    app_file: Annotated[str, Field(description="FastAPI app log file name")] = "app/app.log"
    worker_file: Annotated[str, Field(description="Worker log file name")] = "worker/worker.log"
    level: Annotated[str, Field(description="Loguru logging level")] = "INFO"
    rotation: Annotated[str, Field(description="File rotation size")] = "50 MB"
    retention: Annotated[str, Field(description="Log retention duration")] = "30 days"

    @property
    def app_log_path(self) -> Path:
        return self.dir / self.app_file

    @property
    def worker_log_path(self) -> Path:
        return self.dir / self.worker_file


class StorageSettings(BaseModel):
    dir: Annotated[Path, Field(description="Storage root directory")] = Path("storage")
    temp_file_max_age_seconds: Annotated[
        int, Field(description="Max age of temporary files in seconds before cleanup", ge=60)
    ] = 86400

    @property
    def uploads_dir(self) -> Path:
        """Директорія для завантажень користувачів (похідна від dir)."""
        return self.dir / "uploads"

    @property
    def temp_dir(self) -> Path:
        """Директорія для тимчасових файлів (похідна від dir)."""
        return self.dir / "temp"


class SeedSettings(BaseModel):
    superadmin_username: Annotated[str, Field(description="Initial superadmin username")] = "super_admin"
    superadmin_name: Annotated[str, Field(description="Initial superadmin display name")] = "Super Administrator"
    superadmin_password: Annotated[str, Field(description="Initial superadmin password", min_length=8)] = "super_admin"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
        env_prefix="APP_CONFIG__",
        extra="ignore",
    )

    environment: Annotated[str, Field(description="Application environment: local, staging, production")] = "local"

    db: DbSettings = DbSettings()
    redis: RedisSettings = RedisSettings()
    auth: AuthSettings = AuthSettings()
    api: ApiSettings = ApiSettings()
    arq: ArqSettings = ArqSettings()
    cache: CacheSettings = CacheSettings()
    redis_sets: RedisSetSettings = RedisSetSettings()
    log: LogSettings = LogSettings()
    storage: StorageSettings = StorageSettings()
    seed: SeedSettings = SeedSettings()

    instance_id: Annotated[str, Field(description="Унікальний ідентифікатор інстансу бекенду")] = Field(
        default_factory=lambda: os.getenv("HOSTNAME", "instance-1")
    )
    simulate_latency_ms: Annotated[int, Field(description="Штучна затримка запитів у мілісекундах", ge=0)] = 0

    @property
    def is_testing(self) -> bool:
        """Визначає, чи додаток виконується в тестовому середовищі."""
        return self.environment == "test" or "pytest" in sys.modules

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        """Перевірка криптографічної стійкості налаштувань для бойового середовища."""
        if self.environment in ("production", "prod") and self.auth.bcrypt_rounds < 12:
            raise ValueError(
                f"Критична помилка безпеки: у середовищі '{self.environment}' "
                f"мінімальна кількість раундів bcrypt — 12 (передано: {self.auth.bcrypt_rounds})!"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
