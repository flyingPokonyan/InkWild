from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ---------- 用户端 ----------

class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    title: str
    body: str | None = None
    link: str | None = None
    payload: dict | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    next_before: datetime | None = None


class AnnouncementOut(BaseModel):
    id: str
    title: str
    body: str
    image_url: str | None = None
    level: str
    published_at: datetime | None = None
    read: bool


class AnnouncementListOut(BaseModel):
    items: list[AnnouncementOut]
    next_before: datetime | None = None


class NotificationSummaryOut(BaseModel):
    notifications: int
    announcements: int


# ---------- admin ----------

class AnnouncementCreateIn(BaseModel):
    title: str
    body: str
    level: str = "info"
    image_url: str | None = None
    expires_at: datetime | None = None


class AnnouncementUpdateIn(BaseModel):
    title: str | None = None
    body: str | None = None
    level: str | None = None
    image_url: str | None = None
    expires_at: datetime | None = None


class AnnouncementAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    body: str
    image_url: str | None = None
    level: str
    status: str
    published_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class AnnouncementImageOut(BaseModel):
    image_url: str
