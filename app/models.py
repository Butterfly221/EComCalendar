from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


meeting_participant = Table(
    "meeting_participant",
    Base.metadata,
    Column("meeting_id", Integer, ForeignKey("meeting.id", ondelete="CASCADE"), primary_key=True),
    Column("employee_id", Integer, ForeignKey("employee.id", ondelete="CASCADE"), primary_key=True),
)


class Employee(Base):
    __tablename__ = "employee"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    created_meetings: Mapped[list["Meeting"]] = relationship(
        "Meeting", back_populates="creator", foreign_keys="Meeting.created_by"
    )
    meetings: Mapped[list["Meeting"]] = relationship(
        "Meeting", secondary=meeting_participant, back_populates="participants"
    )


class Meeting(Base):
    __tablename__ = "meeting"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("employee.id"), nullable=False)

    creator: Mapped["Employee"] = relationship("Employee", back_populates="created_meetings", foreign_keys=[created_by])
    participants: Mapped[list["Employee"]] = relationship(
        "Employee", secondary=meeting_participant, back_populates="meetings"
    )