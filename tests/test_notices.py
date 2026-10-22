import pytest

from desktop import dashboard, notices, settings


def test_first_look_at_a_course_only_marks_it():
    fresh, seen = notices.new_since([("c1", "Redes", "2026-10-20T10:00:00Z", "Prova adiada")], {})

    assert fresh == []
    assert seen == {"c1": "2026-10-20T10:00:00Z"}


def test_newer_announcements_are_reported_once():
    found = [
        ("c1", "Redes", "2026-10-22T10:00:00Z", "Aula   amanhã\nno lab 3"),
        ("c1", "Redes", "2026-10-20T10:00:00Z", "Prova adiada")
    ]

    fresh, seen = notices.new_since(found, {"c1": "2026-10-20T10:00:00Z"})

    assert fresh == [("Redes", "Aula amanhã no lab 3")]
    assert notices.new_since(found, seen)[0] == []


class Call:

    def __init__(self, data):
        self.data = data

    def execute(self):
        return self.data


class FakeMural:

    def __init__(self, announcements):
        self.items = announcements

    def courses(self):
        return self

    def announcements(self):
        return self

    def list(self, **kwargs):
        if "courseId" in kwargs:
            assert kwargs["orderBy"] == "updateTime desc"
            return Call({"announcements": self.items})

        return Call({"courses": [{"id": "c1", "name": "Redes"}]})


def test_check_uses_only_connected_accounts_and_remembers(monkeypatch):
    mural = FakeMural([{"updateTime": "2026-10-20T10:00:00Z", "text": "Bem-vindos"}])
    monkeypatch.setattr(notices, "connected", lambda account: account == "eu@discente.uenp.edu.br")
    monkeypatch.setattr(notices, "service", lambda account: mural)

    assert notices.check(["eu@discente.uenp.edu.br", "eu@gmail.com"]) == []

    mural.items = [{"updateTime": "2026-10-22T09:00:00Z", "text": "Trabalho novo no mural"}] + mural.items

    assert notices.check(["eu@discente.uenp.edu.br"]) == [("Redes", "Trabalho novo no mural")]


def test_classroom_accounts_follow_preferences(monkeypatch):
    monkeypatch.setattr(dashboard.google_data, "accounts", lambda: ["eu@gmail.com", "eu@discente.uenp.edu.br"])

    assert dashboard.classroom_accounts() == ["eu@gmail.com", "eu@discente.uenp.edu.br"]

    settings.save({"classroom_accounts": ["eu@discente.uenp.edu.br"]})

    assert dashboard.classroom_accounts() == ["eu@discente.uenp.edu.br"]


def test_dashboard_classroom_reads_only_chosen_accounts_from_last_month(monkeypatch):
    settings.save({"classroom_accounts": ["eu@discente.uenp.edu.br"]})
    monkeypatch.setattr(dashboard, "google_ready", lambda accounts: True)
    asked = {}

    def services(name, version, only):
        asked["only"] = only
        return "serviços"

    def summary(account_services, request, since):
        asked["since_days"] = (dashboard.datetime.now().astimezone() - since).days
        return "Atividades pendentes no Classroom:\n- Relatório"

    monkeypatch.setattr(dashboard.google_data, "services", services)
    monkeypatch.setattr(dashboard.google_data, "classroom_summary", summary)

    assert dashboard.classroom().endswith("Relatório")
    assert asked == {"only": ["eu@discente.uenp.edu.br"], "since_days": dashboard.CLASSROOM_DAYS}


def test_classroom_accounts_must_be_emails():
    with pytest.raises(ValueError):
        settings.save({"classroom_accounts": ["discente"]})
