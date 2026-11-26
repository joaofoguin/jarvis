import google_data
import icloud_data
from desktop import connections


def test_only_saved_logins_are_checked_and_never_interactively(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_ACCOUNTS", "a@b.com")
    monkeypatch.setattr(google_data, "token_file", lambda account, kind="": str(tmp_path / f"token_{kind}.json"))
    (tmp_path / "token_.json").write_text("{}")
    (tmp_path / "token_drive.json").write_text("{}")
    calls = []

    def get_credentials(account, scopes, kind, interactive):
        calls.append((kind, interactive))
        if kind == "drive":
            raise google_data.LoginNeeded("venceu")

    monkeypatch.setattr(google_data, "get_credentials", get_credentials)

    working, problems = connections.check()

    assert calls == [("", False), ("drive", False)]
    assert working == 1
    assert problems == ["Drive de a@b.com: o login venceu; peça uma busca no Drive pelo chat."]


def test_icloud_is_checked_when_configured(monkeypatch):
    monkeypatch.setattr(google_data, "accounts", lambda: [])
    monkeypatch.setenv("ICLOUD_EMAIL", "a@icloud.com")
    monkeypatch.setenv("ICLOUD_APP_PASSWORD", "x")

    def refuse(*args):
        raise RuntimeError("o iCloud recusou o login")

    monkeypatch.setattr(icloud_data, "carddav", refuse)

    assert connections.check() == (0, ["iCloud: o iCloud recusou o login."])


def test_report():
    assert connections.report(0, []) is None
    assert connections.report(3, []) == "Conexões conferidas: 3 funcionando."
    assert connections.report(1, ["x"]).endswith("- x")
