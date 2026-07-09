from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SignupConfigUpdateIn(BaseModel):
    # open / capped / closed
    signup_mode: str | None = None
    signup_cap: int | None = Field(default=None, ge=0)
    # True = 把计数起点重置为 now（开新一批 / 从现在起再放 N 人）
    start_new_batch: bool = False


class SignupStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signup_mode: str
    signup_cap: int
    signup_batch_start: datetime | None = None
    batch_used: int
    batch_remaining: int | None = None
    updated_at: datetime | None = None


class RuntimeConfigUpdateIn(BaseModel):
    llm_global_concurrency: int | None = Field(default=None, ge=1, le=10_000)
    llm_call_timeout_seconds: float | None = Field(default=None, ge=1, le=900)
    llm_call_max_retries: int | None = Field(default=None, ge=0, le=10)
    llm_call_retry_backoff_seconds: float | None = Field(default=None, ge=0, le=60)
    generation_task_active_limit_per_user: int | None = Field(default=None, ge=1, le=1_000)
    image_generation_concurrency: int | None = Field(default=None, ge=1, le=100)
    image_generation_global_concurrency: int | None = Field(default=None, ge=0, le=10_000)
    image_generation_timeout_seconds: float | None = Field(default=None, ge=1, le=900)
    image_generation_quality: str | None = None
    lore_pack_concurrency: int | None = Field(default=None, ge=1, le=100)
    character_batch_concurrency: int | None = Field(default=None, ge=1, le=100)
    events_data_concurrency: int | None = Field(default=None, ge=1, le=100)

    @field_validator("image_generation_quality")
    @classmethod
    def validate_image_quality(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"low", "medium", "high", "auto"}:
            raise ValueError("图片质量必须是 low / medium / high / auto")
        return normalized


class RuntimeConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    llm_global_concurrency: int
    llm_call_timeout_seconds: float
    llm_call_max_retries: int
    llm_call_retry_backoff_seconds: float
    generation_task_active_limit_per_user: int
    image_generation_concurrency: int
    image_generation_global_concurrency: int
    image_generation_timeout_seconds: float
    image_generation_quality: str
    lore_pack_concurrency: int
    character_batch_concurrency: int
    events_data_concurrency: int
    updated_at: datetime | None = None
