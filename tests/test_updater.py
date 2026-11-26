import pytest

import updater


def fake_git(monkeypatch, heads, changed="", fail=None):
    calls = []

    def run(*command, timeout=None):
        calls.append(command)
        args = command[1:]

        if fail and args[0] == fail:
            raise RuntimeError("sem internet")
        if args[0] == "rev-parse":
            return heads.pop(0)
        if args[0] == "log":
            return "Confere os logins\nApaga conversas"
        if args[0] == "diff":
            return changed
        return ""

    monkeypatch.setattr(updater, "run", run)
    return calls


def test_update_lists_new_commits_and_installs_changed_requirements(monkeypatch):
    calls = fake_git(monkeypatch, ["a", "b"], changed="desktop/app.py\nrequirements-desktop.txt")

    result = updater.update()

    assert result == {"changes": ["Confere os logins", "Apaga conversas"], "error": None}
    assert ("git", "pull", "--ff-only") in calls
    assert calls[-1][1:] == ("-m", "pip", "install", "-q", "-r", "requirements-desktop.txt")
    assert updater.last_result() == result
    assert updater.last_result() is None


def test_update_without_changes_skips_pip(monkeypatch):
    calls = fake_git(monkeypatch, ["a", "a"])

    assert updater.update() == {"changes": [], "error": None}
    assert all(command[0] == "git" for command in calls)


def test_failed_pull_still_opens_the_installed_version(monkeypatch):
    fake_git(monkeypatch, ["a"], fail="pull")

    assert updater.update() == {"changes": [], "error": "sem internet"}


@pytest.mark.parametrize("result, text", [
    (None, None),
    ({"changes": [], "error": None}, None),
    ({"changes": ["Apaga conversas"], "error": None}, "Atualizado pelo GitHub:\n- Apaga conversas"),
])
def test_report(result, text):
    assert updater.report(result) == text


def test_report_on_error_mentions_the_old_version():
    assert "versão que já estava" in updater.report({"changes": [], "error": "x"})
