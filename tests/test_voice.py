import sys
import types

import pytest

from desktop import settings, voice


class FakeModel:

    def __init__(self, scores):
        self.scores = iter(scores)

    def reset(self):
        pass

    def predict(self, frame):
        return {"hey_jarvis_v0.1": next(self.scores)}


@pytest.fixture
def fake_sr(monkeypatch):
    # Os testes nunca abrem o microfone nem chamam o Google.
    module = types.SimpleNamespace(
        WaitTimeoutError=type("WaitTimeoutError", (Exception,), {}),
        UnknownValueError=type("UnknownValueError", (Exception,), {}),
        RequestError=type("RequestError", (Exception,), {}),
        Recognizer=lambda: None
    )
    monkeypatch.setitem(sys.modules, "speech_recognition", module)
    return module


def make_voice(**preferences):
    states, heard = [], []
    jarvis = voice.Voice(heard.append, states.append, {**settings.DEFAULTS, **preferences})
    return jarvis, heard, states


def test_settings_fill_defaults_and_ignore_unknown_keys():
    settings.path().write_text('{"voice": "pt-BR-FranciscaNeural", "senha": "x"}', encoding="utf-8")

    assert settings.load() == {**settings.DEFAULTS, "voice": "pt-BR-FranciscaNeural"}


def test_settings_survive_a_broken_file():
    settings.path().write_text("{quebrado", encoding="utf-8")

    assert settings.load() == settings.DEFAULTS


def test_wake_word_needs_a_confident_score(monkeypatch):
    monkeypatch.setattr(voice, "read_frame", lambda source: b"")
    jarvis, _, _ = make_voice()
    jarvis.model = FakeModel([0.1, 0.3, 0.9])

    assert jarvis.wait_for_wake(source=None)


def test_menu_request_skips_the_wake_word(monkeypatch):
    monkeypatch.setattr(voice, "read_frame", lambda source: pytest.fail("não deveria ouvir"))
    jarvis, _, _ = make_voice()
    jarvis.model = FakeModel([])
    jarvis.trigger.set()

    assert jarvis.wait_for_wake(source=None)


def test_turning_off_the_wake_word_stops_listening(monkeypatch):
    jarvis, _, _ = make_voice()
    jarvis.model = FakeModel([0.1])

    def frame(source):
        jarvis.wake_word = False
        return b""

    monkeypatch.setattr(voice, "read_frame", frame)

    assert not jarvis.wait_for_wake(source=None)


def test_conversation_keeps_listening_until_silence(fake_sr, monkeypatch):
    jarvis, heard, states = make_voice()
    phrases = iter(["que horas são", "e amanhã?", None])
    monkeypatch.setattr(jarvis, "listen", lambda recognizer, source: next(phrases))
    jarvis.trigger.set()

    jarvis.converse(source=None)

    assert heard == ["que horas são", "e amanhã?"]
    assert states == ["listening", "thinking", "listening", "thinking", "listening", "idle"]
    assert not jarvis.trigger.is_set()


class FakeRecognizer:

    def __init__(self, error=None):
        self.error = error

    def listen(self, source, timeout, phrase_time_limit):
        if self.error:
            raise self.error
        return "audio"

    def recognize_google(self, audio, language):
        assert language == "pt-BR"
        return "abra o bloco de notas"


def test_listen_returns_the_recognized_phrase(fake_sr):
    jarvis, _, _ = make_voice()

    assert jarvis.listen(FakeRecognizer(), source=None) == "abra o bloco de notas"


def test_silence_or_mumbling_ends_the_conversation(fake_sr):
    jarvis, _, _ = make_voice()

    assert jarvis.listen(FakeRecognizer(fake_sr.WaitTimeoutError()), source=None) is None
    assert jarvis.listen(FakeRecognizer(fake_sr.UnknownValueError()), source=None) is None


def test_recognition_offline_is_said_aloud(fake_sr, monkeypatch):
    jarvis, _, _ = make_voice()
    said = []
    monkeypatch.setattr(jarvis, "say", said.append)

    assert jarvis.listen(FakeRecognizer(fake_sr.RequestError()), source=None) is None
    assert "internet" in said[0]


def test_say_uses_chosen_voice_and_keeps_links_on_screen(monkeypatch):
    jarvis, _, states = make_voice(voice="pt-BR-FranciscaNeural", rate="+10%")
    calls = []
    monkeypatch.setattr(voice, "synthesize", lambda text, name, rate: calls.append((text, name, rate)) or "fala.mp3")
    monkeypatch.setattr(voice, "play", calls.append)

    jarvis.say("Relatório pronto: https://exemplo.com/a.pdf")

    assert calls == [("Relatório pronto: o link está na tela", "pt-BR-FranciscaNeural", "+10%"), "fala.mp3"]
    assert states == ["speaking", "thinking"]


def test_say_stays_quiet_when_spoken_replies_are_off(monkeypatch):
    jarvis, _, states = make_voice(speak_replies=False)
    monkeypatch.setattr(voice, "synthesize", lambda *args: pytest.fail("não deveria falar"))

    jarvis.say("Oi, senhor.")

    assert states == []


def test_voice_failure_keeps_the_answer_on_screen(monkeypatch):
    jarvis, _, states = make_voice()

    def offline(*args):
        raise OSError("sem internet")

    monkeypatch.setattr(voice, "synthesize", offline)

    jarvis.say("Oi, senhor.")

    assert states == ["speaking", "thinking"]
