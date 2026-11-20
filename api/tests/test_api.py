import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["SEED_DEMO"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import validators as v  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

H = {"X-Requested-With": "vitaschedule"}
PW = "Vita#Demo2026"


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(engine)
    with TestClient(app) as c:  # lifespan roda o seed
        yield c


def login(client, email, pw=PW):
    return client.post("/api/auth/login", json={"identifier": email, "password": pw}, headers=H)


def next_date(doc):
    d = v.add_days(v.today().isoformat(), 20)
    while v.weekday_js(d) not in doc["days"]:
        d = v.add_days(d, 1)
    return d


def booking(doc, date, time=None, **kw):
    return {"doctorId": doc["id"], "patientName": "Maria Souza", "cpf": "529.982.247-25", "phone": "(11) 91234-5678",
            "email": "m@x.com", "insurance": "Particular", "date": date, "time": time or doc["slots"][0],
            "consent": True, **kw}


def test_csrf_header_required(client):
    assert client.post("/api/auth/logout").status_code == 403


def test_login_and_me(client):
    assert login(client, "paciente@vitamed.com").status_code == 200
    assert "vs_session" in client.cookies
    me = client.get("/api/auth/me").json()["user"]
    assert me["role"] == "Patient" and "hash" not in str(me)
    client.post("/api/auth/logout", headers=H)
    assert client.get("/api/auth/me").json()["user"] is None


def test_bad_login_generic(client):
    a = login(client, "paciente@vitamed.com", "errada")
    b = login(client, "naoexiste@x.com", "errada")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_double_booking_and_public_flow(client):
    docs = client.get("/api/doctors").json()
    doc = docs[0]
    d = next_date(doc)
    r = client.post("/api/appointments", json=booking(doc, d), headers=H)
    assert r.status_code == 201, r.text
    assert client.post("/api/appointments", json=booking(doc, d), headers=H).status_code == 409
    proto = r.json()["protocol"]
    ok = client.post("/api/appointments/lookup", json={"protocol": proto, "cpf": "52998224725"}, headers=H)
    assert ok.status_code == 200 and ok.json()["patientName"] == "Maria S."
    bad = client.post("/api/appointments/lookup", json={"protocol": proto, "cpf": "11144477735"}, headers=H)
    assert bad.status_code == 404
    busy = client.get("/api/doctors").json()[0]["busy"]
    assert [d, doc["slots"][0]] in busy


def test_validation(client):
    doc = client.get("/api/doctors").json()[1]
    d = next_date(doc)
    assert client.post("/api/appointments", json=booking(doc, d, cpf="111.111.111-11"), headers=H).status_code == 422
    assert client.post("/api/appointments", json=booking(doc, d, insurance="Amil"), headers=H).status_code == 422
    assert client.post("/api/appointments", json=booking(doc, "2020-01-01"), headers=H).status_code == 422
    assert client.post("/api/appointments", json=booking(doc, d, consent=False), headers=H).status_code == 422
    assert client.post("/api/appointments", json=booking(doc, d, extra="x"), headers=H).status_code == 422


def test_rbac_and_ownership(client):
    client.post("/api/auth/logout", headers=H)
    assert client.get("/api/appointments").status_code == 401
    login(client, "paciente@vitamed.com")
    mine = client.get("/api/appointments").json()
    assert mine and all(a["ownerId"] == mine[0]["ownerId"] for a in mine)
    assert client.get("/api/admin/overview").status_code == 403
    assert client.patch("/api/appointments/VIT-8092/status", json={"status": "Faltou"}, headers=H).status_code == 403
    # cancelar agendamento de terceiro
    assert client.post("/api/appointments/VIT-8091/cancel", headers=H).status_code == 404
    assert client.post("/api/appointments/VIT-8092/cancel", headers=H).status_code == 200
    assert client.post("/api/appointments/VIT-8092/cancel", headers=H).status_code == 409


def test_doctor_scope_and_record(client):
    login(client, "mariana.souza@vitamed.com")
    ids = {a["id"] for a in client.get("/api/appointments").json()}
    assert "VIT-8091" not in ids  # paciente de outro médico
    assert client.get("/api/appointments/VIT-8091/record").status_code == 403
    assert client.get("/api/appointments/VIT-8092/record").json()["found"] is True
    d = v.add_days(v.today().isoformat(), 3)
    assert client.post("/api/blocks", json={"start": d, "end": d, "reason": "Folga"}, headers=H).status_code == 201
    assert client.post("/api/blocks", json={"start": d, "end": "2000-01-01", "reason": "x"}, headers=H).status_code == 422


def test_reception_and_admin(client):
    login(client, "recepcao@vitamed.com")
    assert client.patch("/api/appointments/VIT-8091/status", json={"status": "Em atendimento"}, headers=H).status_code == 200
    assert client.patch("/api/appointments/VIT-8091/status", json={"status": "xx"}, headers=H).status_code == 422
    assert len(client.get("/api/appointments").json()) >= 3
    login(client, "admin@vitamed.com")
    ov = client.get("/api/admin/overview").json()
    assert len(ov["users"]) == 4 and ov["audit"]
    me_id = next(u["id"] for u in ov["users"] if u["role"] == "Admin")
    assert client.delete(f"/api/admin/users/{me_id}", headers=H).status_code == 409


def test_login_throttle(client):
    client.post("/api/auth/logout", headers=H)
    codes = [login(client, "throttle@x.com", "x").status_code for _ in range(6)]
    assert codes[-1] == 429


def _req(xff=None, peer="10.0.0.9"):
    from starlette.requests import Request
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def test_client_ip_ignores_forged_forwarded_for(monkeypatch):
    from app.api import client_ip
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    assert client_ip(_req("1.2.3.4")) == "10.0.0.9"  # sem proxy confiável: só vale o par TCP
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    assert client_ip(_req("6.6.6.6, 203.0.113.7")) == "203.0.113.7"  # entrada forjada à esquerda é ignorada
    assert client_ip(_req()) == "10.0.0.9"  # sem cabeçalho: par TCP
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    assert client_ip(_req("203.0.113.7")) == "10.0.0.9"  # cadeia menor que o esperado: não confia


def test_lookup_throttle_not_bypassed_by_forged_forwarded_for(client, monkeypatch):
    from app.api import lookup_throttle
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    lookup_throttle.fails.clear()
    lookup_throttle.locked.clear()
    body = {"protocol": "VIT-ZZZZ9999", "cpf": "52998224725"}
    codes = [client.post("/api/appointments/lookup", json=body, headers={**H, "X-Forwarded-For": f"9.9.9.{i}"}).status_code
             for i in range(6)]
    assert codes[:5] == [404] * 5 and codes[5] == 429
