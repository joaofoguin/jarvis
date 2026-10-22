from datetime import datetime

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
    assert google_data.token_file("eu@gmail.com") == "google_token_eu_gmail_com.json"

    monkeypatch.delenv("GOOGLE_ACCOUNTS")

    assert google_data.accounts() == [None]
    assert google_data.token_file(None) == "google_token.json"


def test_failed_login_does_not_hide_other_accounts():
    ok = FakeCalendar([{"summary": "Aula", "start": {"dateTime": "2026-10-22T08:00:00-03:00"}}])

    text = google_data.agenda_summary(1, [("a@gmail.com", ok), ("b@uenp.edu.br", RuntimeError("access_denied"))])

    assert "Aula [a@gmail.com]" in text
    assert "Não consegui entrar em b@uenp.edu.br: access_denied" in text


def test_services_keeps_going_when_one_login_fails(monkeypatch):
    monkeypatch.setenv("GOOGLE_ACCOUNTS", "a@gmail.com,b@uenp.edu.br")

    def credentials(account):
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
