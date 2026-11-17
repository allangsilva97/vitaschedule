import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
STATUSES = ["Confirmado", "Aguardando", "Em atendimento", "Finalizado", "Faltou", "Cancelado"]
INACTIVE = {"Cancelado", "Faltou"}
CANCELLABLE = {"Confirmado", "Aguardando"}
SLOT_VALUES = {"09:00", "10:15", "14:00", "16:30"}
NAME_RE = re.compile(r"^[^\W\d_][\w .'’-]{2,99}$")
EMAIL_RE = re.compile(r"^[^\s@<>\"'`,;:()\[\]\\]+@[^\s@<>\"'`,;:()\[\]\\]+\.[A-Za-z]{2,}$")
PROTOCOL_RE = re.compile(r"^VIT-[A-Z0-9]{4,8}$")


def digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def valid_name(s: str) -> bool:
    return bool(NAME_RE.match(s)) and not re.search(r"[\d_]", s)


def valid_cpf(cpf: str) -> bool:
    d = digits(cpf)
    if len(d) != 11 or len(set(d)) == 1:
        return False

    def check(n: int) -> int:
        s = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        r = (s * 10) % 11
        return 0 if r == 10 else r

    return check(9) == int(d[9]) and check(10) == int(d[10])


def format_cpf(cpf: str) -> str:
    d = digits(cpf)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def mask_cpf(cpf: str) -> str:
    d = digits(cpf)
    return f"***.{d[3:6]}.{d[6:9]}-**" if len(d) == 11 else "***"


def valid_phone(p: str) -> bool:
    d = digits(p)
    if not re.match(r"^[1-9][1-9]", d):
        return False
    return (len(d) == 10 and d[2] in "2345") or (len(d) == 11 and d[2] == "9")


def format_phone(p: str) -> str:
    d = digits(p)[:11]
    return f"({d[:2]}) {d[2:7]}-{d[7:]}" if len(d) == 11 else f"({d[:2]}) {d[2:6]}-{d[6:]}"


def valid_email(e: str) -> bool:
    return len(e) <= 254 and bool(EMAIL_RE.match(e))


def valid_iso(s: str) -> bool:
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)) and date.fromisoformat(s).isoformat() == s
    except ValueError:
        return False


def today() -> date:
    return datetime.now(TZ).date()


def now_hm() -> str:
    return datetime.now(TZ).strftime("%H:%M")


def add_days(iso: str, n: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=n)).isoformat()


def weekday_js(iso: str) -> int:
    """0=dom ... 6=sáb (mesmo padrão do front)."""
    return (date.fromisoformat(iso).weekday() + 1) % 7
