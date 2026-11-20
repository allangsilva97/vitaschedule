import os
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import validators as v
from .db import get_db
from .models import Appointment, AuditLog, BlockedSlot, Doctor, PatientRecord, User
from .security import (SESSION_COOKIE, SESSION_MINUTES, Throttle, hash_password, make_token, read_token,
                       verify_password)

router = APIRouter(prefix="/api")

PRODUCTION = os.environ.get("APP_ENV") == "production"
DEMO = os.environ.get("SEED_DEMO", "").lower() in ("1", "true", "yes")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Vita#Demo2026")
ROLES = {"Patient", "Reception", "Doctor", "Admin"}

login_throttle = Throttle(5, 5 * 60, 60)
lookup_throttle = Throttle(5, 5 * 60, 60)
booking_throttle = Throttle(10, 10 * 60, 10 * 60)  # cada agendamento anônimo conta como "falha"


def err(status: int, msg: str) -> HTTPException:
    return HTTPException(status_code=status, detail=msg)


def client_ip(request: Request) -> str:
    """IP usado pelos limitadores de tentativas.

    Atrás de proxies de confiança, defina TRUSTED_PROXY_HOPS com quantos proxies ficam na frente do app:
    o IP é a N-ésima entrada de X-Forwarded-For contada da DIREITA, a que o nosso proxy acrescentou. Entradas
    à esquerda vêm do cliente e podem ser forjadas, então nunca valem. Com 0 (padrão) vale só o par TCP.
    """
    hops = int(os.environ.get("TRUSTED_PROXY_HOPS", "0") or 0)
    if hops > 0:
        chain = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(chain) >= hops:
            return chain[-hops]
    return request.client.host if request.client else "?"


def audit(db: Session, user: User | None, action: str, detail: str = "") -> None:
    db.add(AuditLog(user=user.email if user else "anônimo", action=action[:80], detail=detail[:200]))


# --------------------------------------------------------------------------
# Sessão / autorização (sempre conferidas aqui, nunca só no front)
# --------------------------------------------------------------------------
def set_session(response: Response, user_id: int) -> None:
    response.set_cookie(SESSION_COOKIE, make_token(user_id), max_age=SESSION_MINUTES * 60, httponly=True,
                        secure=PRODUCTION, samesite="strict", path="/")


def read_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    uid = read_token(token) if token else None
    return db.get(User, uid) if uid else None


def optional_user(response: Response, user: Annotated[User | None, Depends(read_user)]) -> User | None:
    if user:
        set_session(response, user.id)  # sessão deslizante: renova a cada requisição
    return user


def require(*roles: str):
    def dep(user: Annotated[User | None, Depends(optional_user)], db: Annotated[Session, Depends(get_db)]) -> User:
        if user is None:
            raise err(401, "Sessão expirada. Entre novamente.")
        if user.role not in roles:
            audit(db, user, "Acesso negado", "ação restrita")
            db.commit()
            raise err(403, "Acesso negado: você não tem permissão para esta ação.")
        return user
    return dep


DB = Annotated[Session, Depends(get_db)]
OptUser = Annotated[User | None, Depends(optional_user)]


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role,
            "cpf": u.cpf, "doctorName": u.doctor.name if u.doctor else None}


# --------------------------------------------------------------------------
# Config / auth
# --------------------------------------------------------------------------
@router.get("/config")
def config():
    return {"demo": DEMO, "demoPassword": DEMO_PASSWORD if DEMO else None}


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: DB):
    ident = body.identifier.strip().lower()
    keys = [f"ip:{client_ip(request)}", f"id:{ident}"]
    wait = max(login_throttle.seconds_left(k) for k in keys)
    if wait:
        raise err(429, f"Muitas tentativas. Tente novamente em {wait}s.")

    d = v.digits(ident)
    cond = User.email == ident
    if len(d) == 11:
        cond = cond | (func.replace(func.replace(User.cpf, ".", ""), "-", "") == d)
    user = db.scalars(select(User).where(cond)).first()

    ok = verify_password(body.password, user.password_hash if user else None) and user is not None
    if not ok:
        for k in keys:
            login_throttle.fail(k)
        audit(db, user, "Login falhou", "" if user else "identificador desconhecido")
        db.commit()
        raise err(401, "Credenciais inválidas.")  # mensagem única: não enumera contas
    for k in keys:
        login_throttle.reset(k)
    audit(db, user, "Login", user.role)
    db.commit()
    set_session(response, user.id)
    return {"user": user_out(user)}


@router.post("/auth/logout")
def logout(response: Response, user: Annotated[User | None, Depends(read_user)], db: DB):
    if user:
        audit(db, user, "Logout")
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: OptUser):
    return {"user": user_out(user) if user else None}


# --------------------------------------------------------------------------
# Médicos e disponibilidade (público; não expõe dados de pacientes)
# --------------------------------------------------------------------------
@router.get("/doctors")
def doctors(db: DB):
    today = v.today().isoformat()
    busy: dict[int, list] = {}
    for a in db.scalars(select(Appointment).where(Appointment.date >= today, Appointment.status.not_in(v.INACTIVE))):
        busy.setdefault(a.doctor_id, []).append([a.date, a.time])
    blocks: dict[int, list] = {}
    for b in db.scalars(select(BlockedSlot).where(BlockedSlot.end >= today)):
        blocks.setdefault(b.doctor_id, []).append([b.start, b.end])
    return [{"id": d.id, "name": d.name, "specialty": d.specialty, "rating": d.rating, "avatar": d.avatar,
             "insurance": d.insurance, "days": d.days, "slots": d.slots,
             "busy": busy.get(d.id, []), "blocks": blocks.get(d.id, [])}
            for d in db.scalars(select(Doctor).order_by(Doctor.id))]


# --------------------------------------------------------------------------
# Agendamentos
# --------------------------------------------------------------------------
def appt_out(a: Appointment) -> dict:
    return {"id": a.id, "ownerId": a.owner_id, "patientName": a.patient_name, "cpfMasked": v.mask_cpf(a.patient_cpf),
            "doctorName": a.doctor.name, "specialty": a.doctor.specialty, "date": a.date, "time": a.time,
            "status": a.status, "insurance": a.insurance, "authorizationStatus": a.authorization_status,
            "type": a.type, "reminderDate": a.reminder_date}


class BookingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doctorId: int
    patientName: str | None = Field(default=None, max_length=100)
    cpf: str | None = Field(default=None, max_length=14)
    phone: str = Field(max_length=15)
    email: str = Field(max_length=254)
    insurance: str = Field(max_length=40)
    date: str = Field(max_length=10)
    time: str = Field(max_length=5)
    consent: bool


def new_protocol() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "VIT-" + "".join(secrets.choice(alphabet) for _ in range(8))


@router.post("/appointments", status_code=201)
def create_appointment(body: BookingIn, request: Request, user: OptUser, db: DB):
    if user and user.role not in ("Patient", "Reception"):
        raise err(403, "Seu perfil não pode criar agendamentos.")
    if user is None:
        ip = f"ip:{client_ip(request)}"
        wait = booking_throttle.seconds_left(ip)
        if wait:
            raise err(429, f"Muitos agendamentos seguidos. Tente novamente em {wait}s.")
        booking_throttle.fail(ip)

    doc = db.get(Doctor, body.doctorId)
    if not doc:
        raise err(422, "Profissional inválido.")

    owner_id = None
    if user and user.role == "Patient":  # identidade vem da SESSÃO, nunca do formulário
        name, cpf, owner_id = user.name, user.cpf or "", user.id
    else:
        name = " ".join((body.patientName or "").split())
        cpf = body.cpf or ""
    if not v.valid_name(name):
        raise err(422, "Informe o nome completo (apenas letras, de 3 a 100 caracteres).")
    if not v.valid_cpf(cpf):
        raise err(422, "CPF inválido.")
    phone, email = body.phone.strip(), body.email.strip().lower()
    if not v.valid_phone(phone):
        raise err(422, "Telefone inválido. Informe DDD + número (ex: (11) 91234-5678).")
    if not v.valid_email(email):
        raise err(422, "E-mail inválido.")
    if body.insurance not in doc.insurance:
        raise err(422, "Convênio não atendido por este profissional.")
    if not body.consent:
        raise err(422, "É necessário consentir com o tratamento de dados (LGPD).")

    today = v.today().isoformat()
    if not v.valid_iso(body.date):
        raise err(422, "Selecione uma data válida.")
    if body.date < today:
        raise err(422, "A data da consulta não pode estar no passado.")
    if body.date > v.add_days(today, 365):
        raise err(422, "Agendamentos são aceitos em até 12 meses.")
    if body.time not in v.SLOT_VALUES or body.time not in doc.slots:
        raise err(422, "O profissional não atende neste horário.")
    if v.weekday_js(body.date) not in doc.days:
        raise err(422, "O profissional não atende neste dia da semana.")
    if body.date == today and body.time <= v.now_hm():
        raise err(422, "Este horário já passou. Escolha outro.")
    if db.scalar(select(BlockedSlot.id).where(BlockedSlot.doctor_id == doc.id, BlockedSlot.start <= body.date,
                                              BlockedSlot.end >= body.date)):
        raise err(409, "O profissional não atende nesta data (agenda bloqueada).")

    reminder = v.add_days(body.date, -1)
    for _ in range(5):
        appt = Appointment(
            id=new_protocol(), owner_id=owner_id, doctor_id=doc.id, patient_name=name,
            patient_cpf=v.format_cpf(cpf), phone=v.format_phone(phone), email=email, date=body.date,
            time=body.time, status="Confirmado", insurance=body.insurance,
            authorization_status="N/A (Particular)" if body.insurance == "Particular" else "Pendente Guia",
            reminder_date=reminder if reminder >= today else None, consent_at=datetime.now(timezone.utc))
        db.add(appt)
        try:
            audit(db, user, "Agendamento criado", appt.id)
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if db.scalar(select(Appointment.id).where(
                    Appointment.doctor_id == doc.id, Appointment.date == body.date, Appointment.time == body.time,
                    Appointment.status.not_in(v.INACTIVE))):
                raise err(409, "Este horário já está ocupado. Escolha outro.")
    else:
        raise err(500, "Não foi possível gerar o protocolo. Tente novamente.")

    return {"protocol": appt.id, "doctorName": doc.name, "date": appt.date, "time": appt.time,
            "email": email, "phone": appt.phone, "reminderDate": appt.reminder_date}


@router.get("/appointments")
def list_appointments(user: Annotated[User, Depends(require("Patient", "Reception", "Doctor"))], db: DB):
    q = select(Appointment).order_by(Appointment.created_at.desc())
    if user.role == "Patient":
        q = q.where(Appointment.owner_id == user.id)
    elif user.role == "Doctor":
        q = q.where(Appointment.doctor_id == user.doctor_id)
    return [appt_out(a) for a in db.scalars(q)]


@router.post("/appointments/{protocol}/cancel")
def cancel_appointment(protocol: str, user: Annotated[User, Depends(require("Patient"))], db: DB):
    a = db.get(Appointment, protocol)
    if not a or a.owner_id != user.id:  # propriedade conferida mesmo conhecendo o protocolo
        audit(db, user, "Acesso negado", "cancelamento de agendamento de terceiro")
        db.commit()
        raise err(404, "Agendamento não encontrado.")
    if a.status not in v.CANCELLABLE:
        raise err(409, "Este agendamento não pode mais ser cancelado.")
    a.status = "Cancelado"
    audit(db, user, "Agendamento cancelado", a.id)
    db.commit()
    return appt_out(a)


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


@router.patch("/appointments/{protocol}/status")
def update_status(protocol: str, body: StatusIn, user: Annotated[User, Depends(require("Reception"))], db: DB):
    if body.status not in v.STATUSES:
        raise err(422, "Status inválido.")
    a = db.get(Appointment, protocol)
    if not a:
        raise err(404, "Agendamento não encontrado.")
    a.status = body.status
    audit(db, user, "Status alterado", f"{a.id} -> {body.status}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise err(409, "Este horário já está ocupado por outro agendamento.")
    return appt_out(a)


class LookupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol: str = Field(max_length=12)
    cpf: str = Field(max_length=14)


def mask_name(name: str) -> str:
    parts = name.split()
    return " ".join([parts[0]] + [p[0].upper() + "." for p in parts[1:]]) if parts else ""


@router.post("/appointments/lookup")
def lookup(body: LookupIn, request: Request, db: DB):
    key = f"ip:{client_ip(request)}"
    wait = lookup_throttle.seconds_left(key)
    if wait:
        raise err(429, f"Muitas tentativas. Tente novamente em {wait}s.")
    protocol, cpf = body.protocol.strip().upper(), v.digits(body.cpf)
    if not v.PROTOCOL_RE.match(protocol) or len(cpf) != 11:
        raise err(422, "Informe um protocolo válido (ex: VIT-8092) e o CPF com 11 dígitos.")
    a = db.get(Appointment, protocol)
    if not a or v.digits(a.patient_cpf) != cpf:
        lookup_throttle.fail(key)
        raise err(404, "Nenhum agendamento encontrado para os dados informados.")  # sem revelar qual dado falhou
    lookup_throttle.reset(key)
    return {"id": a.id, "patientName": mask_name(a.patient_name), "status": a.status, "doctorName": a.doctor.name,
            "specialty": a.doctor.specialty, "date": a.date, "time": a.time}


@router.get("/appointments/{protocol}/record")
def patient_record(protocol: str, user: Annotated[User, Depends(require("Doctor"))], db: DB):
    a = db.get(Appointment, protocol)
    if not a or a.doctor_id != user.doctor_id:  # só o médico responsável abre o prontuário
        audit(db, user, "Acesso negado", "prontuário de paciente de outro profissional")
        db.commit()
        raise err(403, "Acesso negado ao prontuário.")
    rec = db.scalar(select(PatientRecord).where(PatientRecord.cpf == a.patient_cpf))
    audit(db, user, "Acesso ao prontuário", a.id)
    db.commit()
    if not rec:
        return {"found": False}
    return {"found": True, "name": rec.name, "insurance": rec.insurance, "notes": rec.notes}


# --------------------------------------------------------------------------
# Bloqueio de agenda (médico, só a própria)
# --------------------------------------------------------------------------
class BlockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str = Field(max_length=10)
    end: str = Field(max_length=10)
    reason: str = Field(max_length=200)


@router.post("/blocks", status_code=201)
def create_block(body: BlockIn, user: Annotated[User, Depends(require("Doctor"))], db: DB):
    if not user.doctor_id:
        raise err(403, "Usuário sem perfil de profissional.")
    if not (v.valid_iso(body.start) and v.valid_iso(body.end)):
        raise err(422, "Datas inválidas.")
    if body.start < v.today().isoformat():
        raise err(422, "A data de início não pode estar no passado.")
    if body.end < body.start:
        raise err(422, "A data final deve ser igual ou posterior à inicial.")
    if body.end > v.add_days(body.start, 365):
        raise err(422, "O bloqueio não pode ultrapassar 365 dias.")
    reason = " ".join(body.reason.split())
    if not 3 <= len(reason) <= 120:
        raise err(422, "Informe um motivo de 3 a 120 caracteres.")
    db.add(BlockedSlot(doctor_id=user.doctor_id, start=body.start, end=body.end, reason=reason))
    audit(db, user, "Agenda bloqueada", f"{body.start} a {body.end}")
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# Administração
# --------------------------------------------------------------------------
@router.get("/admin/overview")
def admin_overview(user: Annotated[User, Depends(require("Admin"))], db: DB):
    users = [{"id": u.id, "name": u.name, "email": u.email, "role": u.role, "twoFactor": u.two_factor}
             for u in db.scalars(select(User).order_by(User.id))]
    log = [{"ts": e.ts.isoformat(), "user": e.user, "action": e.action, "detail": e.detail}
           for e in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(10))]
    month = v.today().isoformat()[:7]
    return {"users": users, "audit": log,
            "appointmentsTotal": db.scalar(select(func.count()).select_from(Appointment)),
            "appointmentsMonth": db.scalar(select(func.count()).select_from(Appointment).where(
                Appointment.date.like(f"{month}-%")))}


@router.post("/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, user: Annotated[User, Depends(require("Admin"))], db: DB):
    target = db.get(User, user_id)
    if not target:
        raise err(404, "Usuário não encontrado.")
    audit(db, user, "Redefinição de senha solicitada", target.email)
    db.commit()
    return {"email": target.email}  # envio de e-mail real ainda não implementado


@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, user: Annotated[User, Depends(require("Admin"))], db: DB):
    target = db.get(User, user_id)
    if not target:
        raise err(404, "Usuário não encontrado.")
    if target.id == user.id:
        raise err(409, "Você não pode remover a própria conta.")
    if target.role == "Admin" and db.scalar(select(func.count()).select_from(User).where(User.role == "Admin")) <= 1:
        raise err(409, "Não é possível remover o último administrador.")
    db.query(Appointment).filter(Appointment.owner_id == target.id).update({Appointment.owner_id: None})
    db.delete(target)
    audit(db, user, "Usuário removido", target.email)
    db.commit()
    return {"ok": True}


@router.get("/healthz")
def healthz(db: DB):
    db.execute(select(1))
    return {"ok": True}
