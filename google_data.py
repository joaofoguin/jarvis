"""Leitura da Google Agenda e do Classroom para a janela de chat (somente leitura)."""

import os
import re
from datetime import datetime, timedelta


SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly"
]

# credentials.json vem do Google Cloud; os tokens são criados no primeiro login. Nenhum vai para o Git.
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")

MAX_ITEMS = 10

# Estados de entrega que ainda precisam de ação do aluno.
PENDING_STATES = ["NEW", "CREATED", "RECLAIMED_BY_STUDENT"]


def accounts():
    """E-mails de GOOGLE_ACCOUNTS (separados por vírgula). Vazio = uma conta, sem e-mail definido."""

    emails = [email.strip() for email in os.getenv("GOOGLE_ACCOUNTS", "").split(",") if email.strip()]
    return emails or [None]


def token_file(account):
    if not account:
        return "google_token.json"

    return "google_token_" + re.sub(r"[^a-zA-Z0-9]+", "_", account) + ".json"


def get_credentials(account):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    path = token_file(account)
    creds = None

    if os.path.exists(path):
        creds = Credentials.from_authorized_user_file(path, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            raise RuntimeError(f"Arquivo {CREDENTIALS_FILE} não encontrado. Veja o guia de configuração do Google.")

        # Abre o navegador para o login do Google; só acontece na primeira vez de cada conta.
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0, **({"login_hint": account} if account else {}))

    with open(path, "w") as file:
        file.write(creds.to_json())

    return creds


def services(name, version):
    """Retorna [(conta, serviço)] para cada conta configurada."""

    from googleapiclient.discovery import build

    return [
        (account, build(name, version, credentials=get_credentials(account), cache_discovery=False))
        for account in accounts()
    ]


def label(account, many):
    # Com uma conta só, não há por que repetir o e-mail em cada linha.
    return f" [{account}]" if many and account else ""


def agenda_summary(days, account_services=None):
    account_services = account_services or services("calendar", "v3")
    many = len(account_services) > 1

    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)

    events = []
    errors = []

    for account, service in account_services:
        try:
            items = service.events().list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=MAX_ITEMS
            ).execute().get("items", [])

        except Exception as error:
            errors.append(f"Não consegui ler a agenda de {account}: {error}")
            continue

        events += [(event_start(item), format_event(item) + label(account, many)) for item in items]

    period = "hoje" if days == 1 else f"nos próximos {days} dias"

    if events:
        events.sort(key=lambda entry: entry[0])
        lines = [f"Sua agenda {period}:"] + [f"- {text}" for _, text in events[:MAX_ITEMS * 2]]
    else:
        lines = [f"Nenhum compromisso na sua agenda {period}, senhor."]

    return "\n".join(lines + errors)


def event_start(item):
    start = item.get("start", {})

    if "dateTime" in start:
        return datetime.fromisoformat(start["dateTime"]).astimezone()

    # Eventos de dia inteiro só têm a data.
    return datetime.fromisoformat(start.get("date", "1970-01-01")).astimezone()


def format_event(item):
    title = item.get("summary", "(sem título)")

    if "dateTime" in item.get("start", {}):
        return f"{event_start(item):%d/%m %H:%M} {title}"

    return f"{event_start(item):%d/%m} (dia todo) {title}"


def classroom_summary(account_services=None):
    account_services = account_services or services("classroom", "v1")
    many = len(account_services) > 1

    pending = []
    errors = []

    for account, service in account_services:
        try:
            pending += [
                (due, course + label(account, many), title)
                for due, course, title in pending_work(service)
            ]

        except Exception as error:
            errors.append(f"Não consegui ler o Classroom de {account}: {error}")

    if pending:
        # Atividades com prazo primeiro, da mais urgente para a menos urgente.
        pending.sort(key=lambda entry: (entry[0] is None, entry[0] or datetime.max))
        lines = ["Atividades pendentes no Classroom:"]

        for due, course, title in pending[:MAX_ITEMS]:
            deadline = f"até {due:%d/%m}" if due else "sem prazo"
            lines.append(f"- {title} ({course}, {deadline})")
    else:
        lines = ["Nenhuma atividade pendente no Classroom, senhor."]

    return "\n".join(lines + errors)


def pending_work(service):
    """Retorna [(prazo, turma, título)] das atividades pendentes de uma conta."""

    courses = service.courses().list(studentId="me", courseStates=["ACTIVE"]).execute().get("courses", [])
    pending = []

    for course in courses:
        submissions = service.courses().courseWork().studentSubmissions().list(
            courseId=course["id"],
            courseWorkId="-",
            userId="me",
            states=PENDING_STATES
        ).execute().get("studentSubmissions", [])

        pending_ids = {item["courseWorkId"] for item in submissions}

        if not pending_ids:
            continue

        work = service.courses().courseWork().list(courseId=course["id"]).execute().get("courseWork", [])

        for item in work:
            if item["id"] in pending_ids:
                pending.append((due_date(item), course["name"], item.get("title", "(sem título)")))

    return pending


def due_date(item):
    date = item.get("dueDate")

    if not date:
        return None

    return datetime(date["year"], date["month"], date["day"])
