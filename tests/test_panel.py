from datetime import date, datetime, timezone

import pytest

import memory
from desktop import panel, settings, skills, usage


def test_save_preferences_validates_and_keeps_known_keys():
    saved = settings.save({"voice": "pt-BR-FranciscaNeural", "rate": "-20%", "accent": "#F5B83F", "extra": 1})

    assert saved == {**settings.DEFAULTS, "voice": "pt-BR-FranciscaNeural", "rate": "-20%", "accent": "#F5B83F"}
    assert settings.load() == saved


@pytest.mark.parametrize("values", [
    {"voice": "pt-BR-Desconhecida"},
    {"rate": "+80%"},
    {"rate": "rápido"},
    {"accent": "red; background: url(x)"},
    {"wake_word": "sim"}
])
def test_invalid_preferences_are_refused_and_not_saved(values):
    with pytest.raises(ValueError):
        settings.save(values)

    assert not settings.path().exists()


def at(day, hour=12):
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


def test_usage_summary_groups_days_and_estimates_cost():
    data = [
        (at(22), "desktop", 1_000_000, 400_000, 100_000),
        (at(21), "alexa", 2_000, 0, 500),
        (at(1), "desktop", 999, 0, 999)
    ]

    summary = usage.summarize(data, date(2026, 10, 22), days=3)

    assert [day["tokens"] for day in summary["days"]] == [0, 2_500, 1_100_000]
    assert summary["days"][-1]["day"] == "2026-10-22"
    assert summary["by_source"] == {"desktop": 1_100_000, "alexa": 2_500}
    assert summary["calls"] == 2
    # 600 mil sem cache, 400 mil em cache e 100 mil de saída, mais a chamada da Alexa.
    assert summary["cost"] == round(0.18 + 0.0024 + 0.12 + (2_000 * 0.3 + 500 * 1.2) / 1_000_000, 4)


@pytest.mark.parametrize("url, name", [
    ("https://github.com/forrestchang/andrej-karpathy-skills", "forrestchang/andrej-karpathy-skills"),
    ("https://github.com/dono/repo.git", "dono/repo"),
    ("https://github.com/dono/repo/", "dono/repo")
])
def test_repo_name_accepts_github_repositories(url, name):
    assert skills.repo_name(url) == name


@pytest.mark.parametrize("url", [
    "https://gitlab.com/dono/repo",
    "https://github.com/dono/repo; rm -rf ~",
    "https://github.com/dono/..",
    "--upload-pack=calc https://github.com/dono/repo",
    "https://github.com/dono"
])
def test_repo_name_refuses_anything_else(url):
    with pytest.raises(ValueError):
        skills.repo_name(url)


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    folder = tmp_path / "workspace"
    folder.mkdir()
    monkeypatch.setenv("JARVIS_WORKSPACE", str(folder))
    return folder


def fake_clone(files):
    def clone(url, destination):
        for name, text in files.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    return clone


def test_add_copies_each_skill_folder_and_remove_undoes_it(workspace, monkeypatch):
    monkeypatch.setattr(skills, "clone", fake_clone({
        "skills/revisar/SKILL.md": "revisar",
        "skills/planejar/SKILL.md": "planejar",
        "README.md": "leia-me"
    }))

    assert skills.add("https://github.com/dono/repo") == ["planejar", "revisar"]
    assert (workspace / ".claude" / "skills" / "revisar" / "SKILL.md").read_text() == "revisar"
    assert skills.installed() == {"dono/repo": ["planejar", "revisar"]}

    skills.remove("dono/repo")

    assert not (workspace / ".claude" / "skills" / "revisar").exists()
    assert skills.installed() == {}


def test_add_never_overwrites_an_existing_skill(workspace, monkeypatch):
    mine = workspace / ".claude" / "skills" / "revisar"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("minha")
    monkeypatch.setattr(skills, "clone", fake_clone({"revisar/SKILL.md": "outra"}))

    with pytest.raises(ValueError, match="revisar"):
        skills.add("https://github.com/dono/repo")

    assert (mine / "SKILL.md").read_text() == "minha"
    assert skills.installed() == {}


def test_repository_without_skills_is_refused(workspace, monkeypatch):
    monkeypatch.setattr(skills, "clone", fake_clone({"CLAUDE.md": "regras"}))

    with pytest.raises(ValueError, match="SKILL.md"):
        skills.add("https://github.com/dono/repo")


class FakeJarvis:

    def __init__(self):
        self.applied = None
        self.quitting = False

    def apply_preferences(self, preferences):
        self.applied = preferences


def test_panel_saves_and_applies_preferences():
    jarvis = FakeJarvis()

    answer = panel.Panel(jarvis, window=None).save_preferences({"wake_word": False})

    assert answer["ok"]["wake_word"] is False
    assert jarvis.applied == answer["ok"]


def test_panel_reports_errors_instead_of_raising():
    answer = panel.Panel(FakeJarvis(), window=None).save_preferences({"accent": "azul"})

    assert answer == {"error": "cor inválida"}


def test_panel_lists_and_forgets_memory():
    memory.remember("contatos", "namorada", "Amor")
    screen = panel.Panel(FakeJarvis(), window=None)

    assert screen.load_panel()["memory"]["contatos"] == {"title": "Contatos", "items": [("namorada", "Amor")]}
    assert screen.forget_memory("contatos", "namorada")["ok"]["contatos"]["items"] == []


def test_panel_usage_error_keeps_panel_working(monkeypatch):
    def offline():
        raise RuntimeError("POSTGRES_URL não encontrada")

    monkeypatch.setattr(usage, "summary", offline)

    assert panel.Panel(FakeJarvis(), window=None).load_usage() == {"error": "POSTGRES_URL não encontrada"}
