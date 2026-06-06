from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


JsonValue = Any


class CaseBoardOp(BaseModel):
    op_type: Literal["set_field", "upsert_list_item", "remove_list_item"]
    path: list[str]
    value: JsonValue = None
    match: dict[str, JsonValue] = Field(default_factory=dict)
    reason: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("path must not be empty")
        if any(not isinstance(part, str) or not part for part in value):
            raise ValueError("path must contain non-empty strings")
        return value

    @model_validator(mode="after")
    def validate_op_shape(self) -> "CaseBoardOp":
        if not _is_json_like(self.value):
            raise ValueError("value must be JSON-like")
        if not _is_json_like(self.match):
            raise ValueError("match must be JSON-like")
        if self.op_type in {"upsert_list_item", "remove_list_item"} and not self.match:
            raise ValueError("list operations require match")
        if self.op_type == "upsert_list_item" and not isinstance(self.value, dict):
            raise ValueError("upsert_list_item requires dict value")
        return self


class CaseBoardHistoryEntry(BaseModel):
    op_type: str
    path: list[str]
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    reason: str | None = None
    before: JsonValue = None
    after: JsonValue = None


def _is_json_like(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_is_json_like(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_like(item) for key, item in value.items())
    return False
