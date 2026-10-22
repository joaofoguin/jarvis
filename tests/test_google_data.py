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

    text = google_data.agenda_summary(2, service)

    assert text.splitlines()[0] == "Sua agenda nos próximos 2 dias:"
    assert "Prova de Cálculo" in text
    assert "23/10 (dia todo) Feriado" in text
    assert service.kwargs["calendarId"] == "primary"
    assert service.kwargs["singleEvents"] is True


def test_empty_agenda_today():
    assert google_data.agenda_summary(1, FakeCalendar([])) == "Nenhum compromisso na sua agenda hoje, senhor."


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

    lines = google_data.classroom_summary(service).splitlines()

    assert lines == [
        "Atividades pendentes no Classroom:",
        "- Relatório (Física, até 25/10)",
        "- Lista 3 (Cálculo, até 30/10)",
        "- Leitura (Física, sem prazo)"
    ]


def test_classroom_without_pending_work():
    service = FakeClassroom(courses=[{"id": "c1", "name": "Cálculo"}], work={}, pending={})

    assert google_data.classroom_summary(service) == "Nenhuma atividade pendente no Classroom, senhor."


def test_due_date():
    assert google_data.due_date({"dueDate": {"year": 2026, "month": 1, "day": 2}}) == datetime(2026, 1, 2)
    assert google_data.due_date({}) is None
