from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
