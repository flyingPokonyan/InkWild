from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class CaseBoardHistory(Base):
    __tablename__ = "case_board_history"
    __table_args__ = (
        Index("idx_case_board_history_session_id", "session_id"),
        Index("idx_case_board_history_session_id_id", "session_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("game_sessions.id"),
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    op_type: Mapped[str] = mapped_column(String(50), nullable=False)
    path: Mapped[list] = mapped_column(JSON, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    before: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
