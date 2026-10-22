import pytest

import whatsapp_app


AMOR = "BEGIN:VCARD\r\nFN:Amor❤️🥵\r\nTEL:+55 14 99687-2005\r\nEND:VCARD"
JULYA = "BEGIN:VCARD\r\nFN:Julya Namorada Jow\r\nTEL:(14) 99635-4039\r\nEND:VCARD"
JULIA = "BEGIN:VCARD\r\nFN:Julia Prima\r\nTEL:(43) 98888-7777\r\nEND:VCARD"


@pytest.mark.parametrize("phone, digits", [
    ("+55 14 99687-2005", "5514996872005"),
    ("(14) 99635-4039", "5514996354039"),
    ("014 99635-4039", "5514996354039"),
    ("+1 415 555 0100", "14155550100"),
])
def test_phone_digits(phone, digits):
    assert whatsapp_app.phone_digits(phone) == digits


def test_recipient_from_contacts():
    assert whatsapp_app.recipient("Amor", [JULYA, AMOR]) == ("Amor❤️🥵", "5514996872005")


def test_recipient_typed_number():
    assert whatsapp_app.recipient("14 99635-4039", []) == ("14 99635-4039", "5514996354039")


def test_ambiguous_recipient_is_refused():
    with pytest.raises(RuntimeError, match="mais de um contato"):
        whatsapp_app.recipient("Julia", [JULIA, JULIA.replace("Prima", "Amiga")])


@pytest.fixture
def desktop(monkeypatch):
    import sys
    import types

    calls = []
    monkeypatch.setattr(whatsapp_app.os, "startfile", calls.append, raising=False)
    monkeypatch.setitem(sys.modules, "keyboard", types.SimpleNamespace(send=lambda key: calls.append(key)))
    monkeypatch.setattr(whatsapp_app.time, "sleep", lambda seconds: None)
    return calls


def test_send_opens_chat_and_presses_enter(desktop, monkeypatch):
    monkeypatch.setattr(whatsapp_app, "foreground_title", lambda: "WhatsApp")

    result = whatsapp_app.send("5514996872005", "Oi amor, já estou em casa")

    assert desktop == ["whatsapp://send?phone=5514996872005&text=Oi%20amor%2C%20j%C3%A1%20estou%20em%20casa", "enter"]
    assert result == 'Mensagem enviada para +5514996872005 pelo WhatsApp: "Oi amor, já estou em casa"'


def test_send_never_presses_enter_in_another_window(desktop, monkeypatch):
    monkeypatch.setattr(whatsapp_app, "foreground_title", lambda: "Bloco de Notas")
    monkeypatch.setattr(whatsapp_app, "OPEN_TIMEOUT", -1)

    result = whatsapp_app.send("5514996872005", "oi")

    assert "enter" not in desktop
    assert "não apertei Enter" in result
