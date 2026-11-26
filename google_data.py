"""Leitura da Google Agenda e do Classroom para a janela de chat (somente leitura)."""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from router import normalize


CALENDAR_WRITE = "https://www.googleapis.com/auth/calendar.events"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    # Criar, mudar e apagar eventos, sempre depois de um "sim" no chat.
    CALENDAR_WRITE,
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly"
]

# YouTube pede um login separado, só na conta do canal, para não refazer o login das outras contas.
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly"
]

# O Google devolve classroom.coursework.me.readonly com o nome antigo
# (classroom.student-submissions.me.readonly). É o mesmo acesso, então aceitamos.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# credentials.json vem do Google Cloud; os tokens são criados no primeiro login. Nenhum vai para o Git.
# Ficam na pasta do projeto, de onde quer que o JARVIS seja aberto (um atalho, por exemplo).
FOLDER = Path(__file__).resolve().parent


def credentials_file():
    # Lido na hora: o .env pode ser carregado depois que este módulo é importado.
    return FOLDER / (os.getenv("GOOGLE_CREDENTIALS") or "credentials.json")

MAX_ITEMS = 10

# Tempo máximo esperando o login no navegador, para uma conta não travar as outras.
LOGIN_TIMEOUT = 120

# Estados de entrega que ainda precisam de ação do aluno.
PENDING_STATES = ["NEW", "CREATED", "RECLAIMED_BY_STUDENT"]


def accounts(request=""):
    """E-mails de GOOGLE_ACCOUNTS (separados por vírgula). Vazio = uma conta, sem e-mail definido.

    Se o pedido citar parte de um e-mail ("conta discente", "uenp"), só as contas citadas.
    """

    emails = [email.strip() for email in os.getenv("GOOGLE_ACCOUNTS", "").split(",") if email.strip()]
    words = {word for word in re.findall(r"\w+", request.lower()) if len(word) >= 4}
    mentioned = [email for email in emails if words & set(re.split(r"[@._-]+", email.lower()))]

    return mentioned or emails or [None]


def token_file(account, kind=""):
    suffix = f"_{kind}" if kind else ""
    name = f"google_token{suffix}.json" if not account else (
        "google_token_" + re.sub(r"[^a-zA-Z0-9]+", "_", account) + suffix + ".json"
    )

    return str(FOLDER / name)


class LoginNeeded(RuntimeError):
    pass


class WrongAccount(RuntimeError):
    pass


def signed_in_email(creds, scopes):
    """O e-mail da conta que de fato fez o login, ou None se as permissões não permitem saber."""

    from googleapiclient.discovery import build

    # A agenda principal tem o e-mail da conta como id; o Drive informa o dono.
    if "https://www.googleapis.com/auth/calendar.readonly" in scopes:
        calendar = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return calendar.calendars().get(calendarId="primary").execute()["id"]

    if "https://www.googleapis.com/auth/drive" in scopes:
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        return drive.about().get(fields="user(emailAddress)").execute()["user"]["emailAddress"]

    return None


def check_account(account, creds, scopes):
    """No navegador dá para entrar com outra conta do Google; aí o JARVIS leria a conta errada."""

    email = account and signed_in_email(creds, scopes)

    if email and email.lower() != account.lower():
        raise WrongAccount(f"o login de {account} foi feito com {email}")


def get_credentials(account, scopes=SCOPES, kind="", interactive=True):
    """Credenciais da conta. Com interactive=False (telas automáticas), nunca abre o navegador:
    se o login precisar ser refeito, levanta LoginNeeded."""

    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    path = token_file(account, kind)
    creds = None

    if os.path.exists(path):
        creds = Credentials.from_authorized_user_file(path, scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())

        except RefreshError:
            # Acesso revogado ou senha trocada: o token salvo não serve mais.
            creds = None

    if not (creds and creds.valid):
        if not interactive:
            raise LoginNeeded(f"O login do Google de {account or 'sua conta'} precisa ser refeito. Peça pelo chat.")

        if not credentials_file().exists():
            raise RuntimeError(f"Arquivo {credentials_file()} não encontrado. Veja o guia de configuração do Google.")

        # Abre o navegador para o login do Google; só acontece na primeira vez de cada conta.
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file()), scopes)
        creds = flow.run_local_server(
            port=0,
            timeout_seconds=LOGIN_TIMEOUT,
            success_message="Login concluído. Pode fechar esta janela e voltar ao JARVIS.",
            **({"login_hint": account} if account else {})
        )

        try:
            check_account(account, creds, scopes)

        except WrongAccount as error:
            raise WrongAccount(f"{error}. Peça de novo e, no navegador, escolha {account}.") from None

    with open(path, "w") as file:
        file.write(creds.to_json())

    return creds


def services(name, version, request="", only=None, interactive=True):
    """Retorna [(conta, serviço)] para cada conta (ou só as de `only`). Se o login falhar, o serviço é o erro."""

    from googleapiclient.discovery import build

    result = []

    for account in only or accounts(request):
        try:
            result.append((account, build(name, version, credentials=get_credentials(account, interactive=interactive), cache_discovery=False)))

        except Exception as error:
            result.append((account, error))

    return result


def short_error(error):
    # Erros da API do Google trazem um JSON enorme; o motivo basta para o chat.
    return str(getattr(error, "reason", None) or error)[:200]


def login_error(account, error):
    who = account or "sua conta"
    return f"Não consegui entrar em {who}: {short_error(error) or 'o login não foi concluído a tempo'}"


def label(account, many):
    # Com uma conta só, não há por que repetir o e-mail em cada linha.
    return f" [{account}]" if many and account else ""


# Texto de cada linha mostrada (evento ou atividade) → link dela no Google, para o clique e o "abra...".
LINKS = {}


def find_link(name):
    """(texto, link) da linha mostrada mais recente que contém o nome, ou None."""

    wanted = normalize(name)

    for text, link in reversed(list(LINKS.items())):
        if wanted and wanted in normalize(text):
            return text, link

    return None


def agenda_summary(days, account_services=None, request=""):
    account_services = account_services or services("calendar", "v3", request)
    many = len(account_services) > 1

    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)

    events = []
    errors = []

    for account, service in account_services:
        if isinstance(service, Exception):
            errors.append(login_error(account, service))
            continue

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
            errors.append(f"Não consegui ler a agenda de {account}: {short_error(error)}")
            continue

        for item in items:
            text = format_event(item) + label(account, many)
            events.append((event_start(item), text))
            if item.get("htmlLink"):
                LINKS[text] = item["htmlLink"]

    period = "hoje" if days == 1 else f"nos próximos {days} dias"

    if events:
        events.sort(key=lambda entry: entry[0])
        lines = [f"Sua agenda {period}:"] + [f"- {text}" for _, text in events[:MAX_ITEMS * 2]]
    elif len(errors) < len(account_services):
        lines = [f"Nenhum compromisso na sua agenda {period}, senhor."]
    else:
        lines = []

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


def classroom_summary(account_services=None, request="", since=None):
    """Atividades pendentes; com `since`, só as criadas a partir dessa data."""

    account_services = account_services or services("classroom", "v1", request)
    many = len(account_services) > 1

    pending = []
    errors = []

    for account, service in account_services:
        if isinstance(service, Exception):
            errors.append(login_error(account, service))
            continue

        try:
            pending += [
                (due, course + label(account, many), title, link)
                for due, course, title, link in pending_work(service, since)
            ]

        except Exception as error:
            errors.append(f"Não consegui ler o Classroom de {account}: {short_error(error)}")

    if pending:
        # Atividades com prazo primeiro, da mais urgente para a menos urgente.
        pending.sort(key=lambda entry: (entry[0] is None, entry[0] or datetime.max))
        lines = ["Atividades pendentes no Classroom:"]

        for due, course, title, link in pending[:MAX_ITEMS]:
            deadline = f"até {due:%d/%m}" if due else "sem prazo"
            text = f"{title} ({course}, {deadline})"
            lines.append(f"- {text}")
            if link:
                LINKS[text] = link
    elif len(errors) < len(account_services):
        lines = ["Nenhuma atividade pendente no Classroom, senhor."]
    else:
        lines = []

    return "\n".join(lines + errors)


def pending_work(service, since=None):
    """Retorna [(prazo, turma, título, link)] das atividades pendentes de uma conta."""

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
            if item["id"] in pending_ids and (not since or created_at(item) >= since):
                pending.append((due_date(item), course["name"], item.get("title", "(sem título)"), item.get("alternateLink")))

    return pending


def parse_when(value):
    """Data e hora em ISO ("2026-11-27T14:00"); sem fuso, vale o horário do notebook."""

    when = datetime.fromisoformat(value)
    return when if when.tzinfo else when.astimezone()


def event_times(start, end):
    start = parse_when(start)
    end = parse_when(end) if end else start + timedelta(hours=1)
    return {"start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}}


def find_event(name, account_services):
    """(conta, serviço, evento) do próximo evento com esse nome, de ontem em diante."""

    since = (datetime.now().astimezone() - timedelta(days=1)).isoformat()

    for account, service in account_services:
        if isinstance(service, Exception):
            continue

        items = service.events().list(
            calendarId="primary", q=name, timeMin=since, singleEvents=True, orderBy="startTime", maxResults=5
        ).execute().get("items", [])

        if items:
            return account, service, items[0]

    raise RuntimeError(f"não achei o evento \"{name}\" na sua agenda")


def create_event(service, title, start, end=""):
    event = service.events().insert(calendarId="primary", body={"summary": title, **event_times(start, end)}).execute()
    return f"Pronto, senhor. Criei {format_event(event)} na agenda."


def update_event(service, event, title="", start="", end=""):
    changes = {"summary": title} if title else {}

    if start:
        changes.update(event_times(start, end))

    event = service.events().patch(calendarId="primary", eventId=event["id"], body=changes).execute()
    return f"Pronto, senhor. O evento agora é {format_event(event)}."


def delete_event(service, event):
    service.events().delete(calendarId="primary", eventId=event["id"]).execute()
    return f"Pronto, senhor. Apaguei {format_event(event)} da agenda."


def created_at(item):
    return datetime.fromisoformat(item.get("creationTime", "1970-01-01T00:00:00Z").replace("Z", "+00:00"))


def due_date(item):
    date = item.get("dueDate")

    if not date:
        return None

    return datetime(date["year"], date["month"], date["day"])


def youtube_account(request):
    """A conta citada no pedido; senão YOUTUBE_ACCOUNT; senão a primeira conta."""

    candidates = accounts(request)

    if len(candidates) == 1:
        return candidates[0]

    return os.getenv("YOUTUBE_ACCOUNT") or candidates[0]


def youtube_summary(request="", youtube=None, analytics=None):
    if not youtube:
        from googleapiclient.discovery import build

        creds = get_credentials(youtube_account(request), YOUTUBE_SCOPES, "youtube")
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

    channels = youtube.channels().list(part="snippet,statistics,contentDetails", mine=True).execute().get("items", [])

    if not channels:
        return "Essa conta do Google não tem um canal do YouTube, senhor."

    channel = channels[0]
    stats = channel.get("statistics", {})
    uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    lines = [
        f"Canal {channel['snippet']['title']}: {number(stats.get('subscriberCount'))} inscritos, "
        f"{number(stats.get('viewCount'))} visualizações no total."
    ]

    playlist = youtube.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=5).execute()
    ids = [item["contentDetails"]["videoId"] for item in playlist.get("items", [])]

    if not ids:
        return "\n".join(lines + ["O canal ainda não tem vídeos."])

    videos = youtube.videos().list(part="snippet,statistics", id=",".join(ids)).execute().get("items", [])

    # Vídeos removidos ou privados continuam na lista de envios, mas não voltam com os dados.
    if not videos:
        return "\n".join(lines + ["Não consegui ler os vídeos recentes; eles podem estar privados ou removidos."])

    latest = videos[0]
    published = datetime.fromisoformat(latest["snippet"]["publishedAt"].replace("Z", "+00:00"))
    video_stats = latest.get("statistics", {})

    lines += [
        "",
        f"Último vídeo: \"{latest['snippet']['title']}\" (publicado em {published:%d/%m/%Y})",
        f"- Visualizações: {number(video_stats.get('viewCount'))}",
        f"- Curtidas: {number(video_stats.get('likeCount'))}",
        f"- Comentários: {number(video_stats.get('commentCount'))}"
    ]

    lines += video_analytics(analytics, latest["id"], published)

    if len(videos) > 1:
        lines += ["", "Outros vídeos recentes:"]
        lines += [
            f"- {video['snippet']['title']}: {number(video.get('statistics', {}).get('viewCount'))} visualizações"
            for video in videos[1:]
        ]

    return "\n".join(lines)


def video_analytics(analytics, video_id, published):
    """Métricas de retenção do YouTube Analytics. Os dados chegam com 2 ou 3 dias de atraso."""

    metrics = "estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,shares"

    try:
        report = analytics.reports().query(
            ids="channel==MINE",
            startDate=f"{published:%Y-%m-%d}",
            endDate=f"{datetime.now():%Y-%m-%d}",
            metrics=metrics,
            filters=f"video=={video_id}"
        ).execute()

    except Exception as error:
        return [f"- Não consegui ler o YouTube Analytics: {short_error(error)}"]

    rows = report.get("rows") or []

    if not rows:
        return ["- O YouTube Analytics ainda não tem dados deste vídeo (eles chegam com 2 ou 3 dias de atraso)."]

    minutes, duration, percentage, subscribers, shares = rows[0]

    return [
        f"- Tempo assistido: {number(minutes)} minutos",
        f"- Duração média de visualização: {int(duration) // 60}:{int(duration) % 60:02d}",
        f"- Porcentagem média assistida: {percentage:.0f}%",
        f"- Inscritos ganhos: {number(subscribers)}",
        f"- Compartilhamentos: {number(shares)}"
    ]


def number(value):
    if value is None:
        return "?"

    return f"{int(float(value)):,}".replace(",", ".")
