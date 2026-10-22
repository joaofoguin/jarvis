import importlib
import sys
import types

import pytest


class FakeWindow:

    def __init__(self):
        self.calls = []
        self.visible = False

    def evaluate_js(self, script):
        self.calls.append(script)

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False


@pytest.fixture
def app(monkeypatch):
    # O app real abre janelas e o ícone do Windows; nos testes, só a lógica.
    for name in ["keyboard", "pystray", "webview"]:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))

    monkeypatch.delitem(sys.modules, "desktop.app", raising=False)
    return importlib.import_module("desktop.app")


@pytest.fixture
def jarvis(app):
    from desktop import settings

    return app.Jarvis(settings.load(), FakeWindow(), FakeWindow())


def test_text_is_sent_to_javascript_as_safe_strings(app):
    window = FakeWindow()

    app.call_js(window, "addMessage", "jarvis", 'Oi "senhor"</script>')

    assert window.calls == ['addMessage("jarvis", "Oi \\"senhor\\"</script>")']


def test_typed_message_and_answer_go_to_chat_and_history(app, jarvis, monkeypatch):
    monkeypatch.setattr(app, "reply_to", lambda text, history: ("Brasília, senhor.", None))

    jarvis.send("capital do Brasil?")

    assert jarvis.chat.calls == ['addMessage("user", "capital do Brasil?")', 'addMessage("jarvis", "Bras\\u00edlia, senhor.")']
    assert jarvis.history == [
        {"role": "user", "content": "capital do Brasil?"},
        {"role": "assistant", "content": "Brasília, senhor."}
    ]


def test_spoken_question_is_answered_aloud_with_task_result(app, jarvis, monkeypatch):
    monkeypatch.setattr(app, "reply_to", lambda text, history: ("Gerando, senhor.", lambda: "Relatório pronto."))
    said = []
    monkeypatch.setattr(jarvis.voice, "say", said.append)

    jarvis.answer_aloud("relatório do youtube")

    assert said == ["Gerando, senhor.", "Relatório pronto."]
    assert jarvis.history[-1] == {"role": "assistant", "content": "Relatório pronto."}


def test_voice_state_reaches_orb_and_chat(jarvis):
    jarvis.show_state("listening")

    assert jarvis.orb.calls == ['setState("listening")']
    assert jarvis.chat.calls == ['setState("listening")']


def test_clicking_the_orb_asks_the_voice_to_listen(jarvis):
    jarvis.talk()

    assert jarvis.voice.trigger.is_set()


def test_closing_the_chat_only_hides_it_until_quitting(jarvis):
    jarvis.toggle_chat()
    assert jarvis.chat.visible

    assert jarvis.closing() is False
    assert not jarvis.chat.visible

    jarvis.quitting = True
    assert jarvis.closing() is True


def test_saved_preferences_apply_without_restarting(jarvis):
    from desktop import settings

    jarvis.apply_preferences({**settings.DEFAULTS, "accent": "#A98BFF", "voice": "pt-BR-FranciscaNeural", "wake_word": False})

    assert jarvis.voice.voice == "pt-BR-FranciscaNeural"
    assert not jarvis.voice.wake_word
    assert jarvis.orb.calls == ['setAccent("#A98BFF")']
    assert jarvis.chat.calls == ['setAccent("#A98BFF")']


def test_answers_go_to_the_history_file(app, jarvis, monkeypatch):
    from desktop import dashboard

    monkeypatch.setattr(app, "reply_to", lambda text, history: ("Às ordens.", None))

    jarvis.send("oi")

    assert dashboard.history()[0]["text"] == "oi"
    assert dashboard.history()[0]["answer"] == "Às ordens."


def test_only_web_links_are_opened(app, jarvis, monkeypatch):
    opened = []
    monkeypatch.setattr(app.webbrowser, "open", opened.append)

    jarvis.open_link("https://news.google.com/x")
    jarvis.open_link("file:///C:/Windows/System32/calc.exe")

    assert opened == ["https://news.google.com/x"]
