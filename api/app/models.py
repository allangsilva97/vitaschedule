from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Doctor(Base):
    __tablename__ = "doctors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    specialty: Mapped[str] = mapped_column(String(60))
    rating: Mapped[str] = mapped_column(String(60), default="")
    avatar: Mapped[str] = mapped_column(String(4))
    insurance: Mapped[list] = mapped_column(JSON)  # ["Unimed", ...]
    days: Mapped[list] = mapped_column(JSON)       # 0=dom ... 6=sáb
    slots: Mapped[list] = mapped_column(JSON)      # ["09:00", ...]


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    role: Mapped[str] = mapped_column(String(20))  # Patient | Reception | Doctor | Admin
    cpf: Mapped[str | None] = mapped_column(String(14), nullable=True)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("doctors.id"), nullable=True)
    two_factor: Mapped[bool] = mapped_column(Boolean, default=False)
    password_hash: Mapped[str] = mapped_column(String(300))
    doctor: Mapped[Doctor | None] = relationship(lazy="joined")


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)  # protocolo VIT-XXXXXXXX
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    patient_name: Mapped[str] = mapped_column(String(100))
    patient_cpf: Mapped[str] = mapped_column(String(14))
    phone: Mapped[str | None] = mapped_column(String(15), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    date: Mapped[str] = mapped_column(String(10))  # ISO yyyy-mm-dd
    time: Mapped[str] = mapped_column(String(5))   # HH:MM
    status: Mapped[str] = mapped_column(String(20), default="Confirmado")
    insurance: Mapped[str] = mapped_column(String(40))
    authorization_status: Mapped[str] = mapped_column(String(40))
    type: Mapped[str] = mapped_column(String(40), default="Consulta Presencial")
    reminder_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    doctor: Mapped[Doctor] = relationship(lazy="joined")

    __table_args__ = (
        # Garante no banco que dois agendamentos ativos não ocupem o mesmo horário (anti-corrida).
        Index(
            "uq_active_slot", "doctor_id", "date", "time", unique=True,
            postgresql_where=text("status NOT IN ('Cancelado', 'Faltou')"),
            sqlite_where=text("status NOT IN ('Cancelado', 'Faltou')"),
        ),
        Index("ix_appointments_cpf", "patient_cpf"),
    )


class BlockedSlot(Base):
    __tablename__ = "blocked_slots"
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    start: Mapped[str] = mapped_column(String(10))
    end: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(120))


class PatientRecord(Base):
    __tablename__ = "patient_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    cpf: Mapped[str] = mapped_column(String(14), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(15), nullable=True)
    insurance: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(String(200), default="")
