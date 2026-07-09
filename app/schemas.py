from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Employee ───────────────────────────────────────────────

class EmployeeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


# ── Meeting ────────────────────────────────────────────────

class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    start_time: datetime
    end_time: datetime
    created_by: int
    participant_ids: list[int] = Field(..., min_length=1)

    @field_validator("end_time")
    @classmethod
    def end_must_be_after_start(cls, v: datetime, info: object) -> datetime:  # noqa: D102
        start = info.data.get("start_time")  # type: ignore[union-attr]
        if start is not None and v <= start:
            raise ValueError("end_time must be after start_time")
        return v


class MeetingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    start_time: datetime
    end_time: datetime
    created_by: int
    participants: list[EmployeeRead]