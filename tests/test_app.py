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


class FakeOrb:

    def __init__(self):
        self.state = "idle"
        self.accent = None

    def set_state(self, state):
        self.state = state

    def set_accent(self, color):
        self.accent = color


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

    return app.Jarvis(settings.load(), FakeOrb(), FakeWindow())


def test_text_is_sent_to_javascript_as_safe_strings(app):
    window = FakeWindow()

    app.call_js(window, "addMessage", "jarvis", 'Oi "senhor"</script>')

    assert window.calls == ['addMessage("jarvis", "Oi \\"senhor\\"</script>")']


def test_typed_message_and_answer_go_to_chat_and_history(app, jarvis, monkeypatch):
    monkeypatch.setattr(app, "reply_to", lambda text, history, record: ("Brasília, senhor.", None))

    jarvis.send("capital do Brasil?")

    assert jarvis.chat.calls == ['addMessage("user", "capital do Brasil?")', 'addMessage("jarvis", "Bras\\u00edlia, senhor.")']
    assert jarvis.history == [
        {"role": "user", "content": "capital do Brasil?"},
        {"role": "assistant", "content": "Brasília, senhor."}
    ]


def test_spoken_question_is_answered_aloud_with_task_result(app, jarvis, monkeypatch):
    monkeypatch.setattr(app, "reply_to", lambda text, history, record: ("Gerando, senhor.", lambda: "Relatório pronto."))
    said = []
    monkeypatch.setattr(jarvis.voice, "say", said.append)

    jarvis.answer_aloud("relatório do youtube")

    assert said == ["Gerando, senhor.", "Relatório pronto."]
    assert jarvis.history[-1] == {"role": "assistant", "content": "Relatório pronto."}


def test_executed_actions_go_to_history(app, jarvis, monkeypatch):
    def reply_to(text, history, record):
        record({"role": "system", "content": "Ação executada: google_agenda:1"})

        def task():
            record({"role": "system", "content": "Ação executada: open_app:notepad"})
            return "Pronto."

        return "Um momento.", task

    monkeypatch.setattr(app, "reply_to", reply_to)

    jarvis.send("agenda e bloco de notas")

    assert jarvis.history == [
        {"role": "user", "content": "agenda e bloco de notas"},
        {"role": "system", "content": "Ação executada: google_agenda:1"},
        {"role": "assistant", "content": "Um momento."},
        {"role": "system", "content": "Ação executada: open_app:notepad"},
        {"role": "assistant", "content": "Pronto."}
    ]


def test_unexpected_error_is_shown_instead_of_killing_the_thread(app, jarvis, monkeypatch):
    def broken(text, history, record):
        raise OSError("disco cheio")

    monkeypatch.setattr(app, "reply_to", broken)

    jarvis.answer("oi")

    assert jarvis.chat.calls == ['addMessage("jarvis", "Desculpe, senhor. Algo deu errado: disco cheio")']


def test_voice_state_reaches_orb_and_chat(jarvis):
    jarvis.show_state("listening")

    assert jarvis.orb.state == "listening"
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
    assert jarvis.orb.accent == "#A98BFF"
    assert jarvis.chat.calls == ['setAccent("#A98BFF")']


def test_answers_go_to_the_history_file(app, jarvis, monkeypatch):
    from desktop import dashboard

    monkeypatch.setattr(app, "reply_to", lambda text, history, record: ("Às ordens.", None))

    jarvis.send("oi")

    assert dashboard.history()[0]["entries"][-1]["text"] == "oi"
    assert dashboard.history()[0]["entries"][-1]["answer"] == "Às ordens."


def test_only_web_links_are_opened(app, jarvis, monkeypatch):
    opened = []
    monkeypatch.setattr(app.webbrowser, "open", opened.append)

    jarvis.open_link("https://news.google.com/x")
    jarvis.open_link("file:///C:/Windows/System32/calc.exe")

    assert opened == ["https://news.google.com/x"]



def test_voice_and_chat_requests_do_not_interleave(app, jarvis, monkeypatch):
    import threading
    import time

    inside = []
    overlaps = []

    def slow_reply(text, history):
        if inside:
            overlaps.append(text)
        inside.append(text)
        time.sleep(0.05)
        inside.remove(text)
        return "ok", None

    monkeypatch.setattr(app, "reply_to", slow_reply)
    threads = [threading.Thread(target=jarvis.answer, args=(text,)) for text in ("sim", "manda oi")]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]

    assert overlaps == []


def test_app_runs_the_queue_agent_until_quitting(app, jarvis, monkeypatch):
    served = []
    lock = object()
    monkeypatch.setattr(app.agent, "start", lambda: lock)
    monkeypatch.setattr(app.agent, "serve", lambda lock, stop: served.append((lock, stop)))

    app.run_agent(jarvis)

    assert served == [(lock, jarvis.stopping)]


def test_app_skips_the_agent_when_another_is_running(app, jarvis, monkeypatch):
    monkeypatch.setattr(app.agent, "start", lambda: "outro agente já está rodando neste computador")
    monkeypatch.setattr(app.agent, "serve", lambda *args: pytest.fail("não deveria rodar"))

    app.run_agent(jarvis)


def test_spoken_request_deletes_history_without_reaching_the_ai(app, jarvis, monkeypatch):
    from desktop import dashboard

    monkeypatch.setattr(app, "reply_to", lambda text, history, record: ("Às ordens.", None))
    jarvis.send("conversa captada sem querer")
    monkeypatch.setattr(app, "reply_to", lambda *args: pytest.fail("não deveria ir para a IA"))
    spoken = []

    jarvis.answer("apague o que eu acabei de dizer", say=spoken.append)

    assert dashboard.history() == []
    assert jarvis.history == []
    assert spoken == ["Pronto, senhor. Apaguei 1 pedido(s) do histórico."]


def test_connections_are_checked_after_opening_without_login(app, jarvis, monkeypatch):
    from desktop import connections

    monkeypatch.setattr(app, "CONNECTIONS_DELAY", 0)
    monkeypatch.setattr(connections, "check", lambda: (1, ["Drive de a@b.com: o login venceu; peça uma busca no Drive pelo chat."]))
    notified = []
    icon = types.SimpleNamespace(notify=lambda text, title: notified.append(title))

    app.check_connections(jarvis, icon)

    assert "Conex\\u00f5es com problema" in jarvis.chat.calls[-1]
    assert notified == ["JARVIS"]


def test_update_result_is_shown_after_opening(app, jarvis, monkeypatch):
    from desktop import connections

    monkeypatch.setattr(app, "CONNECTIONS_DELAY", 0)
    monkeypatch.setattr(app.updater, "last_result", lambda: {"changes": ["Apaga conversas"], "error": None})
    monkeypatch.setattr(connections, "check", lambda: (0, []))

    app.check_connections(jarvis, types.SimpleNamespace(notify=lambda text, title: None))

    assert jarvis.chat.calls == ['addMessage("jarvis", "Atualizado pelo GitHub:\\n- Apaga conversas")']
