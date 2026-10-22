"""Leitura da Google Agenda e do Classroom para a janela de chat (somente leitura)."""

import os
from datetime import datetime, timedelta


SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly"
]

# credentials.json vem do Google Cloud; o token é criado no primeiro login. Nenhum dos dois vai para o Git.
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")
TOKEN_FILE = os.getenv("GOOGLE_TOKEN", "google_token.json")

MAX_ITEMS = 10

# Estados de entrega que ainda precisam de ação do aluno.
PENDING_STATES = ["NEW", "CREATED", "RECLAIMED_BY_STUDENT"]


def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            raise RuntimeError(f"Arquivo {CREDENTIALS_FILE} não encontrado. Veja o guia de configuração do Google.")

        # Abre o navegador para o login do Google; só acontece na primeira vez.
        creds = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES).run_local_server(port=0)

    with open(TOKEN_FILE, "w") as file:
        file.write(creds.to_json())

    return creds


def build_service(name, version):
    from googleapiclient.discovery import build

    return build(name, version, credentials=get_credentials(), cache_discovery=False)


def agenda_summary(days, service=None):
    service = service or build_service("calendar", "v3")

    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)

    items = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=MAX_ITEMS
    ).execute().get("items", [])

    period = "hoje" if days == 1 else f"nos próximos {days} dias"

    if not items:
        return f"Nenhum compromisso na sua agenda {period}, senhor."

    lines = [f"Sua agenda {period}:"] + [f"- {format_event(item)}" for item in items]
    return "\n".join(lines)


def format_event(item):
    title = item.get("summary", "(sem título)")
    start = item.get("start", {})

    if "dateTime" in start:
        when = datetime.fromisoformat(start["dateTime"]).astimezone()
        return f"{when:%d/%m %H:%M} {title}"

    # Eventos de dia inteiro só têm a data.
    when = datetime.fromisoformat(start.get("date", "1970-01-01"))
    return f"{when:%d/%m} (dia todo) {title}"


def classroom_summary(service=None):
    service = service or build_service("classroom", "v1")

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

    if not pending:
        return "Nenhuma atividade pendente no Classroom, senhor."

    # Atividades com prazo primeiro, da mais urgente para a menos urgente.
    pending.sort(key=lambda entry: (entry[0] is None, entry[0] or datetime.max))

    lines = ["Atividades pendentes no Classroom:"]

    for due, course, title in pending[:MAX_ITEMS]:
        deadline = f"até {due:%d/%m}" if due else "sem prazo"
        lines.append(f"- {title} ({course}, {deadline})")

    return "\n".join(lines)


def due_date(item):
    date = item.get("dueDate")

    if not date:
        return None

    return datetime(date["year"], date["month"], date["day"])
