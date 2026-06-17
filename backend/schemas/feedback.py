from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------- 用户端 ----------

class FeedbackCreateIn(BaseModel):
    category: str  # bug / suggestion
    content: str = Field(min_length=1, max_length=4000)
    image: str | None = None  # base64 data URL（可选截图）
    page_url: str | None = Field(default=None, max_length=500)
    contact: str | None = Field(default=None, max_length=200)


# ---------- admin ----------

class FeedbackAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None = None
    category: str
    content: str
    image_url: str | None = None
    page_url: str | None = None
    contact: str | None = None
    user_agent: str | None = None
    status: str
    admin_note: str | None = None
    reply: str | None = None
    created_at: datetime
    updated_at: datetime


class FeedbackUpdateIn(BaseModel):
    status: str | None = None  # new / triaged / resolved
    admin_note: str | None = None  # 内部备注
    reply: str | None = None  # 回复用户（对外，进通知）


# ---------- 用户线程视角 ----------

class FeedbackEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str  # status / reply
    status: str | None = None
    body: str | None = None
    created_at: datetime


class FeedbackThreadOut(BaseModel):
    id: str
    category: str
    content: str
    image_url: str | None = None
    status: str
    created_at: datetime
    events: list[FeedbackEventOut]
