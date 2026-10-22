import pytest

import browser


def thread(viewer, seen, items, **extra):
    return {
        "viewer_id": viewer,
        "last_seen_at": {str(viewer): {"timestamp": str(seen)}},
        "items": [{"user_id": user, "timestamp": str(time)} for user, time in items],
        **extra
    }


def test_unread_counts_only_new_messages_from_others():
    data = {"inbox": {"threads": [
        thread(1, 100, [(2, 300), (2, 200), (2, 50)], users=[{"username": "maria"}]),
        thread(1, 100, [(1, 300), (3, 90)], users=[{"username": "joao"}]),
        thread(1, 100, [(4, 150)], thread_title="Grupo da sala"),
    ]}}

    assert browser.unread_summary(data) == (
        "Mensagens novas no Instagram:\n- maria: 2 mensagens\n- Grupo da sala: 1 mensagem"
    )


def test_no_unread_messages():
    assert browser.unread_summary({"inbox": {"threads": []}}) == "Nenhuma mensagem nova no Instagram, senhor."


def test_instagram_error_is_raised():
    with pytest.raises(RuntimeError, match="login_required"):
        browser.unread_summary({"message": "login_required", "status": "fail"})


def test_contact_aliases(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APELIDOS", "namorada:Amor, mae:Mãe")

    assert browser.contact_name("minha namorada") == "Amor"
    assert browser.contact_name("minha mãe") == "Mãe"
    assert browser.contact_name("Pedro") == "Pedro"
