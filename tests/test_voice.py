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
        AudioSource=object,
        Recognizer=types.SimpleNamespace
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
    monkeypatch.setattr(voice, "synthesize", lambda text, name, rate, part: calls.append((text, name, rate)) or "fala.mp3")
    monkeypatch.setattr(voice, "play", lambda path, cancel: calls.append(path))

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


class FakeInputStream:

    def __init__(self, **options):
        self.options = options
        self.events = []

    def start(self):
        self.events.append("start")

    def stop(self):
        self.events.append("stop")

    def close(self):
        self.events.append("close")

    def read(self, size):
        return bytearray(b"\x01\x00" * size), False


def test_microphone_reads_16khz_mono_without_pyaudio(fake_sr, monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(RawInputStream=FakeInputStream))

    with voice.microphone() as source:
        assert source.stream.read(4) == b"\x01\x00" * 4
        assert source.input.options == {"samplerate": 16000, "blocksize": voice.FRAME, "channels": 1, "dtype": "int16"}

    assert source.input.events == ["start", "stop", "close"]
    assert source.stream is None


def test_clicking_again_cancels_the_conversation(fake_sr, monkeypatch):
    jarvis, heard, states = make_voice()
    fake_sr.Recognizer = types.SimpleNamespace

    def listen(recognizer, source):
        # O segundo clique chega enquanto ele ouve.
        jarvis.toggle()
        return "isso foi captado sem querer"

    monkeypatch.setattr(jarvis, "listen", listen)
    jarvis.trigger.set()

    jarvis.converse(source=None)

    assert heard == []
    assert states == ["listening", "idle"]
    assert not jarvis.busy and not jarvis.cancel.is_set()


def test_click_starts_listening_when_idle():
    jarvis, _, _ = make_voice()

    jarvis.toggle()

    assert jarvis.trigger.is_set()
    assert not jarvis.cancel.is_set()


def test_cancelled_microphone_stops_reading(fake_sr, monkeypatch):
    import threading

    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(RawInputStream=FakeInputStream))
    cancel = threading.Event()

    with voice.microphone(cancel) as source:
        cancel.set()
        with pytest.raises(voice.Cancelled):
            source.stream.read(4)


def test_cancelled_reply_is_not_spoken(monkeypatch):
    jarvis, _, _ = make_voice()
    monkeypatch.setattr(voice, "synthesize", lambda *args: pytest.fail("não deveria falar"))
    jarvis.cancel.set()

    jarvis.say("Resposta")


def test_long_answers_are_spoken_in_parts_and_cut(monkeypatch):
    jarvis, _, _ = make_voice()
    synthesized, played = [], []
    monkeypatch.setattr(voice, "synthesize", lambda text, name, rate, part: synthesized.append(text) or f"{part}.mp3")
    monkeypatch.setattr(voice, "play", lambda path, cancel: played.append(path))

    jarvis.say("Hoje você tem três eventos. " + "Reunião às dez horas na sala de aula. " * 20)

    assert len(synthesized) > 1
    assert played == [f"{n}.mp3" for n in range(len(synthesized))]
    assert synthesized[-1].endswith("O resto está na tela, senhor.")
    assert sum(len(text) for text in synthesized) < voice.SPOKEN_LIMIT + 60


def test_jarvis_voice_is_antonio_with_lower_pitch():
    from desktop import settings

    assert "jarvis" in settings.VOICES
    assert voice.VOICE_PRESETS["jarvis"][0] in settings.VOICES


def test_a_short_pause_does_not_end_the_request(fake_sr, monkeypatch):
    jarvis, heard, _ = make_voice()
    used = []

    def listen(recognizer, source):
        used.append(recognizer.pause_threshold)
        return None

    monkeypatch.setattr(jarvis, "listen", listen)

    jarvis.converse(source=None)

    assert used == [voice.PAUSE_THRESHOLD]
    assert voice.PAUSE_THRESHOLD > 1


def test_closed_orb_stops_listening(fake_sr, monkeypatch):
    jarvis, heard, states = make_voice()
    jarvis.model = FakeModel([0.0] * 10)

    def listen(recognizer, source):
        # O orbe é fechado no meio da conversa.
        jarvis.pause(True)
        return "conversa em volta"

    monkeypatch.setattr(jarvis, "listen", listen)
    monkeypatch.setattr(voice, "read_frame", lambda source: b"")
    jarvis.trigger.set()

    jarvis.converse(source=None)

    assert heard == [] and not jarvis.trigger.is_set()
    jarvis.wake_word = True
    assert jarvis.wait_for_wake(source=None) is False

    jarvis.pause(False)
    assert not jarvis.paused
