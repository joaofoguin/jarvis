from datetime import datetime
from pathlib import Path

import pytest

import google_data


class Call:
    def __init__(self, result, calls=None, name=None):
        self.result = result
        self.calls = calls
        self.name = name

    def execute(self):
        return self.result


class FakeCalendar:
    def __init__(self, items):
        self.items = items
        self.kwargs = None

    def events(self):
        return self

    def list(self, **kwargs):
        self.kwargs = kwargs
        return Call({"items": self.items})


def test_agenda_formats_timed_and_all_day_events():
    service = FakeCalendar([
        {"summary": "Prova de Cálculo", "start": {"dateTime": "2026-10-22T14:00:00-03:00"}},
        {"summary": "Feriado", "start": {"date": "2026-10-23"}}
    ])

    text = google_data.agenda_summary(2, [(None, service)])

    assert text.splitlines()[0] == "Sua agenda nos próximos 2 dias:"
    assert "Prova de Cálculo" in text
    assert "23/10 (dia todo) Feriado" in text
    assert service.kwargs["calendarId"] == "primary"
    assert service.kwargs["singleEvents"] is True


def test_empty_agenda_today():
    assert google_data.agenda_summary(1, [(None, FakeCalendar([]))]) == "Nenhum compromisso na sua agenda hoje, senhor."


class FakeClassroom:
    """Imita courses(), courseWork() e studentSubmissions() do cliente do Google."""

    def __init__(self, courses, work, pending):
        self.data = {"courses": courses, "work": work, "pending": pending}
        self.level = "courses"

    def courses(self):
        return self

    def courseWork(self):
        clone = FakeClassroom(**self.data)
        clone.level = "work"
        return clone

    def studentSubmissions(self):
        clone = FakeClassroom(**self.data)
        clone.level = "submissions"
        return clone

    def list(self, **kwargs):
        if self.level == "courses":
            return Call({"courses": self.data["courses"]})

        if self.level == "submissions":
            ids = self.data["pending"].get(kwargs["courseId"], [])
            return Call({"studentSubmissions": [{"courseWorkId": i} for i in ids]})

        return Call({"courseWork": self.data["work"].get(kwargs["courseId"], [])})


def test_classroom_lists_only_pending_work_sorted_by_due_date():
    service = FakeClassroom(
        courses=[{"id": "c1", "name": "Cálculo"}, {"id": "c2", "name": "Física"}],
        work={
            "c1": [
                {"id": "w1", "title": "Lista 3", "dueDate": {"year": 2026, "month": 10, "day": 30}},
                {"id": "w2", "title": "Lista 2 (entregue)"}
            ],
            "c2": [
                {"id": "w3", "title": "Relatório", "dueDate": {"year": 2026, "month": 10, "day": 25}},
                {"id": "w4", "title": "Leitura"}
            ]
        },
        pending={"c1": ["w1"], "c2": ["w3", "w4"]}
    )

    lines = google_data.classroom_summary([(None, service)]).splitlines()

    assert lines == [
        "Atividades pendentes no Classroom:",
        "- Relatório (Física, até 25/10)",
        "- Lista 3 (Cálculo, até 30/10)",
        "- Leitura (Física, sem prazo)"
    ]


def test_classroom_without_pending_work():
    service = FakeClassroom(courses=[{"id": "c1", "name": "Cálculo"}], work={}, pending={})

    assert google_data.classroom_summary([(None, service)]) == "Nenhuma atividade pendente no Classroom, senhor."


def test_due_date():
    assert google_data.due_date({"dueDate": {"year": 2026, "month": 1, "day": 2}}) == datetime(2026, 1, 2)
    assert google_data.due_date({}) is None


def test_agenda_merges_accounts_in_time_order():
    personal = FakeCalendar([{"summary": "Academia", "start": {"dateTime": "2026-10-22T18:00:00-03:00"}}])
    school = FakeCalendar([{"summary": "Aula", "start": {"dateTime": "2026-10-22T08:00:00-03:00"}}])

    lines = google_data.agenda_summary(1, [("eu@gmail.com", personal), ("eu@uenp.edu.br", school)]).splitlines()

    assert "Aula [eu@uenp.edu.br]" in lines[1]
    assert "Academia [eu@gmail.com]" in lines[2]


class BrokenCalendar:
    def events(self):
        raise RuntimeError("acesso bloqueado")


def test_one_account_failing_does_not_hide_the_others():
    ok = FakeCalendar([{"summary": "Aula", "start": {"dateTime": "2026-10-22T08:00:00-03:00"}}])

    text = google_data.agenda_summary(1, [("a@gmail.com", ok), ("b@uenp.edu.br", BrokenCalendar())])

    assert "Aula [a@gmail.com]" in text
    assert "Não consegui ler a agenda de b@uenp.edu.br: acesso bloqueado" in text


def test_classroom_labels_courses_by_account():
    service = FakeClassroom(
        courses=[{"id": "c1", "name": "Cálculo"}],
        work={"c1": [{"id": "w1", "title": "Lista 3"}]},
        pending={"c1": ["w1"]}
    )
    empty = FakeClassroom(courses=[], work={}, pending={})

    text = google_data.classroom_summary([("eu@uenp.edu.br", service), ("eu@gmail.com", empty)])

    assert "- Lista 3 (Cálculo [eu@uenp.edu.br], sem prazo)" in text


def test_accounts_and_token_files(monkeypatch):
    monkeypatch.setenv("GOOGLE_ACCOUNTS", "eu@gmail.com, joao.lima@discente.uenp.edu.br")

    assert google_data.accounts() == ["eu@gmail.com", "joao.lima@discente.uenp.edu.br"]
    assert Path(google_data.token_file("eu@gmail.com")).name == "google_token_eu_gmail_com.json"

    monkeypatch.delenv("GOOGLE_ACCOUNTS")

    assert google_data.accounts() == [None]
    assert Path(google_data.token_file(None)).name == "google_token.json"


def test_failed_login_does_not_hide_other_accounts():
    ok = FakeCalendar([{"summary": "Aula", "start": {"dateTime": "2026-10-22T08:00:00-03:00"}}])

    text = google_data.agenda_summary(1, [("a@gmail.com", ok), ("b@uenp.edu.br", RuntimeError("access_denied"))])

    assert "Aula [a@gmail.com]" in text
    assert "Não consegui entrar em b@uenp.edu.br: access_denied" in text


def test_services_keeps_going_when_one_login_fails(monkeypatch):
    monkeypatch.setenv("GOOGLE_ACCOUNTS", "a@gmail.com,b@uenp.edu.br")

    def credentials(account, **kwargs):
        if account == "b@uenp.edu.br":
            raise RuntimeError("bloqueado")
        return None

    monkeypatch.setattr(google_data, "get_credentials", credentials)
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *args, **kwargs: "serviço")

    result = google_data.services("calendar", "v3")

    assert result[0] == ("a@gmail.com", "serviço")
    assert isinstance(result[1][1], RuntimeError)


def test_accounts_mentioned_in_request(monkeypatch):
    monkeypatch.setenv("GOOGLE_ACCOUNTS", "joaopedrosrlima@gmail.com,joao.lima@discente.uenp.edu.br,basedobit01@gmail.com")

    assert google_data.accounts("tarefas na minha conta discente") == ["joao.lima@discente.uenp.edu.br"]
    assert google_data.accounts("agenda da uenp") == ["joao.lima@discente.uenp.edu.br"]
    assert len(google_data.accounts("o que tenho hoje")) == 3


class ApiError(Exception):
    reason = "Google Classroom API has not been used in project 123 before or it is disabled."


class FailingClassroom:
    def courses(self):
        raise ApiError("<HttpError 403 ... JSON enorme ...>")


def test_api_errors_are_short_and_do_not_claim_nothing_pending():
    text = google_data.classroom_summary([("eu@uenp.edu.br", FailingClassroom())])

    assert text == (
        "Não consegui ler o Classroom de eu@uenp.edu.br: "
        "Google Classroom API has not been used in project 123 before or it is disabled."
    )


class FakeYouTube:
    def __init__(self, videos):
        self.videos_data = videos

    def channels(self):
        return self

    def playlistItems(self):
        return FakePlaylist([video["id"] for video in self.videos_data])

    def videos(self):
        return FakeVideos(self.videos_data)

    def list(self, **kwargs):
        return Call({"items": [{
            "snippet": {"title": "Na Base do Bit"},
            "statistics": {"subscriberCount": "1234", "viewCount": "56789"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}
        }]})


class FakePlaylist:
    def __init__(self, ids):
        self.ids = ids

    def list(self, **kwargs):
        return Call({"items": [{"contentDetails": {"videoId": i}} for i in self.ids]})


class FakeVideos:
    def __init__(self, videos):
        self.data = videos

    def list(self, **kwargs):
        return Call({"items": self.data})


class FakeAnalytics:
    def __init__(self, rows):
        self.rows = rows
        self.kwargs = None

    def reports(self):
        return self

    def query(self, **kwargs):
        self.kwargs = kwargs
        return Call({"rows": self.rows})


def video(video_id, title, views):
    return {
        "id": video_id,
        "snippet": {"title": title, "publishedAt": "2026-10-15T18:00:00Z"},
        "statistics": {"viewCount": views, "likeCount": "40", "commentCount": "7"}
    }


def test_youtube_summary_with_analytics():
    analytics = FakeAnalytics([[1500.0, 95, 42.3, 12, 5]])
    youtube = FakeYouTube([video("v1", "Montei um PC", "2500"), video("v2", "Vídeo antigo", "900")])

    text = google_data.youtube_summary("", youtube, analytics)

    assert "Canal Na Base do Bit: 1.234 inscritos, 56.789 visualizações no total." in text
    assert 'Último vídeo: "Montei um PC" (publicado em 15/10/2026)' in text
    assert "- Visualizações: 2.500" in text
    assert "- Duração média de visualização: 1:35" in text
    assert "- Porcentagem média assistida: 42%" in text
    assert "- Vídeo antigo: 900 visualizações" in text
    assert analytics.kwargs["filters"] == "video==v1"


def test_youtube_summary_without_analytics_yet():
    text = google_data.youtube_summary("", FakeYouTube([video("v1", "Novo", "10")]), FakeAnalytics([]))

    assert "ainda não tem dados deste vídeo" in text


def test_youtube_account_choice(monkeypatch):
    monkeypatch.setenv("GOOGLE_ACCOUNTS", "joaopedrosrlima@gmail.com,basedobit01@gmail.com")
    monkeypatch.setenv("YOUTUBE_ACCOUNT", "basedobit01@gmail.com")

    assert google_data.youtube_account("insights do meu vídeo") == "basedobit01@gmail.com"
    assert google_data.youtube_account("youtube da conta joaopedrosrlima") == "joaopedrosrlima@gmail.com"
    assert Path(google_data.token_file("basedobit01@gmail.com", "youtube")).name == "google_token_basedobit01_gmail_com_youtube.json"


def test_classroom_since_keeps_only_recent_pending_work():
    from datetime import datetime, timezone

    service = FakeClassroom(
        courses=[{"id": "c1", "name": "Redes"}],
        work={"c1": [
            {"id": "w1", "title": "Relatório novo", "creationTime": "2026-10-20T10:00:00.000Z"},
            {"id": "w2", "title": "Lista antiga", "creationTime": "2026-08-01T10:00:00.000Z"},
            {"id": "w3", "title": "Nova, mas entregue", "creationTime": "2026-10-21T10:00:00.000Z"}
        ]},
        pending={"c1": ["w1", "w2"]}
    )

    text = google_data.classroom_summary([(None, service)], since=datetime(2026, 9, 22, tzinfo=timezone.utc))

    assert text.splitlines() == ["Atividades pendentes no Classroom:", "- Relatório novo (Redes, sem prazo)"]


class ExpiredCredentials:
    valid = False
    expired = True
    refresh_token = "antigo"

    def refresh(self, request):
        from google.auth.exceptions import RefreshError

        # O Google recusa tokens de apps em teste depois de 7 dias.
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    def to_json(self):
        return "{}"


def revoked_token(monkeypatch, tmp_path):
    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setattr(google_data, "token_file", lambda account, kind="": str(token))
    monkeypatch.setattr("google.oauth2.credentials.Credentials.from_authorized_user_file", lambda path, scopes: ExpiredCredentials())


def test_revoked_token_never_opens_login_from_automatic_screens(monkeypatch, tmp_path):
    revoked_token(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        lambda *args: pytest.fail("não deveria abrir o login")
    )

    with pytest.raises(google_data.LoginNeeded):
        google_data.get_credentials("eu@gmail.com", interactive=False)


def test_revoked_token_logs_in_again_from_the_chat(monkeypatch, tmp_path):
    revoked_token(monkeypatch, tmp_path)
    monkeypatch.setenv("GOOGLE_CREDENTIALS", str(tmp_path / "token.json"))

    class Flow:
        def run_local_server(self, **kwargs):
            return ExpiredCredentials()

    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", lambda *args: Flow())
    monkeypatch.setattr(google_data, "signed_in_email", lambda creds, scopes: "Eu@gmail.com")

    assert isinstance(google_data.get_credentials("eu@gmail.com"), ExpiredCredentials)


def test_login_with_another_google_account_is_refused_and_not_saved(monkeypatch, tmp_path):
    revoked_token(monkeypatch, tmp_path)
    monkeypatch.setenv("GOOGLE_CREDENTIALS", str(tmp_path / "token.json"))
    saved = []

    class Flow:
        def run_local_server(self, **kwargs):
            creds = ExpiredCredentials()
            creds.to_json = lambda: saved.append(1) or "{}"
            return creds

    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", lambda *args: Flow())
    monkeypatch.setattr(google_data, "signed_in_email", lambda creds, scopes: "pessoal@gmail.com")

    with pytest.raises(google_data.WrongAccount, match="feito com pessoal@gmail.com"):
        google_data.get_credentials("joao@discente.uenp.edu.br")

    assert saved == []


def test_google_files_live_in_the_project_folder_wherever_the_app_starts(monkeypatch, tmp_path):
    monkeypatch.setattr(google_data, "FOLDER", tmp_path / "jarvis")
    monkeypatch.setenv("GOOGLE_CREDENTIALS", "minhas_credenciais.json")

    assert google_data.token_file("eu@gmail.com") == str(tmp_path / "jarvis" / "google_token_eu_gmail_com.json")
    assert google_data.credentials_file() == tmp_path / "jarvis" / "minhas_credenciais.json"


def test_youtube_summary_when_recent_videos_are_private_or_removed():
    youtube = FakeYouTube([video("v1", "Privado", "10")])
    youtube.videos = lambda: FakeVideos([])

    text = google_data.youtube_summary("", youtube, FakeAnalytics([]))

    assert "privados ou removidos" in text
