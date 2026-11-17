"""Dados de demonstração (fictícios). Só roda quando SEED_DEMO=true e o banco está vazio."""
import os

from sqlalchemy import select

from . import validators as v
from .db import SessionLocal
from .models import Appointment, Doctor, PatientRecord, User
from .security import hash_password

DOCTORS = [
    ("Dra. Mariana Souza", "Cardiologia", "4.9 (124 avaliações)", "MS", ["Unimed", "Bradesco Saúde", "Particular"], [1, 3, 5], ["09:00", "10:15", "14:00", "16:30"]),
    ("Dr. Carlos Eduardo", "Ortopedia", "4.8 (98 avaliações)", "CE", ["SulAmérica", "Unimed", "Particular"], [2, 4, 5], ["09:00", "10:15", "14:00"]),
    ("Dra. Juliana Mendes", "Dermatologia", "5.0 (215 avaliações)", "JM", ["Particular", "Amil"], [1, 2, 3, 4, 5], ["14:00", "16:30"]),
    ("Dr. Roberto Alves", "Pediatria", "4.9 (160 avaliações)", "RA", ["Unimed", "Amil", "Bradesco Saúde", "Particular"], [1, 2, 4], ["09:00", "10:15", "14:00"]),
    ("Dra. Fernanda Lima", "Ginecologia", "4.9 (189 avaliações)", "FL", ["SulAmérica", "Particular"], [3, 5], ["10:15", "14:00", "16:30"]),
]


def seed() -> None:
    if os.environ.get("SEED_DEMO", "").lower() not in ("1", "true", "yes"):
        return
    pw = hash_password(os.environ.get("DEMO_PASSWORD", "Vita#Demo2026"))
    with SessionLocal() as db:
        if db.scalar(select(Doctor.id).limit(1)):
            return
        docs = [Doctor(name=n, specialty=s, rating=r, avatar=a, insurance=i, days=d, slots=sl)
                for n, s, r, a, i, d, sl in DOCTORS]
        db.add_all(docs)
        db.flush()
        mariana = docs[0]
        ana = User(name="Ana Beatriz Silva", email="paciente@vitamed.com", role="Patient", cpf="123.456.789-09",
                   two_factor=True, password_hash=pw)
        db.add_all([
            ana,
            User(name="Carla Recepção", email="recepcao@vitamed.com", role="Reception", password_hash=pw),
            User(name="Dra. Mariana Souza", email="mariana.souza@vitamed.com", role="Doctor", doctor_id=mariana.id,
                 two_factor=True, password_hash=pw),
            User(name="Admin Gestão", email="admin@vitamed.com", role="Admin", two_factor=True, password_hash=pw),
        ])
        db.flush()
        today = v.today().isoformat()
        by_name = {d.name: d for d in docs}
        sample = [  # (protocolo, dono, paciente, cpf, médico, dia+, hora, status, convênio, guia)
            ("VIT-8092", ana.id, "Ana Beatriz Silva", "123.456.789-09", "Dra. Mariana Souza", 7, "14:00", "Aguardando", "Unimed", "Autorizado"),
            ("VIT-8091", None, "Lucas Ferreira", "987.654.321-00", "Dr. Carlos Eduardo", 8, "10:15", "Confirmado", "Particular", "N/A (Particular)"),
            ("VIT-8089", None, "João Pedro Santos", "789.321.654-91", "Dr. Roberto Alves", 9, "09:00", "Confirmado", "Unimed", "Autorizado"),
        ]
        for pid, owner, name, cpf, doc, plus, hour, status, ins, auth in sample:
            # usa a data real do dia da semana atendido pelo médico mais próximo de hoje+plus
            d = v.add_days(today, plus)
            while v.weekday_js(d) not in by_name[doc].days:
                d = v.add_days(d, 1)
            db.add(Appointment(id=pid, owner_id=owner, doctor_id=by_name[doc].id, patient_name=name, patient_cpf=cpf,
                               date=d, time=hour, status=status, insurance=ins, authorization_status=auth))
        db.add_all([
            PatientRecord(cpf="123.456.789-09", name="Ana Beatriz Silva", phone="(11) 98765-4321",
                          insurance="Unimed (Carteirinha #49821)", notes="Alérgica a dipirona. Histórico de hipertensão leve."),
            PatientRecord(cpf="987.654.321-00", name="Lucas Ferreira", phone="(11) 97123-8899",
                          insurance="Particular", notes="Atleta amador. Lesão prévia no joelho direito."),
        ])
        db.commit()
