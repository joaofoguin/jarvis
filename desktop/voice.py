"""Voz do JARVIS no notebook: ouve "Hey Jarvis", entende português e responde falando.

A palavra de ativação é detectada no próprio notebook (openWakeWord), sem mandar áudio
para fora. Só o que você fala depois dela vai para o reconhecimento de voz do Google.
A resposta é lida por uma voz neural da Microsoft (edge-tts).
"""

import asyncio
import re
import tempfile
import threading
from pathlib import Path


SAMPLE_RATE = 16000

# 80 ms de áudio, o pedaço que o openWakeWord analisa de cada vez.
FRAME = 1280

WAKE_MODEL = "hey_jarvis"
WAKE_THRESHOLD = 0.5

# Depois de responder, o JARVIS espera esse tempo (em segundos) por mais uma fala,
# sem precisar de "Hey Jarvis" de novo. Assim dá para conversar.
FOLLOW_UP_TIMEOUT = 6

PHRASE_LIMIT = 15

URL_PATTERN = re.compile(r"https?://\S+")


def microphone():
    """O microfone padrão pelo sounddevice, no formato que o SpeechRecognition espera.

    O sounddevice já vem pronto para qualquer versão do Python no Windows, sem compilar nada.
    """

    import sounddevice
    import speech_recognition as sr

    class Microphone(sr.AudioSource):
        SAMPLE_WIDTH = 2
        CHUNK = FRAME

        def __init__(self):
            self.SAMPLE_RATE = SAMPLE_RATE
            self.input = sounddevice.RawInputStream(samplerate=SAMPLE_RATE, blocksize=FRAME, channels=1, dtype="int16")
            self.stream = None

        def __enter__(self):
            self.input.start()
            self.stream = self
            return self

        def __exit__(self, *error):
            self.input.stop()
            self.input.close()
            self.stream = None

        def read(self, size):
            data, _ = self.input.read(size)
            return bytes(data)

    return Microphone()


def read_frame(source):
    import numpy

    return numpy.frombuffer(source.stream.read(FRAME), dtype=numpy.int16)


def wake_model():
    import openwakeword.utils
    from openwakeword.model import Model

    # Baixa o modelo só na primeira vez.
    openwakeword.utils.download_models([WAKE_MODEL])
    return Model(wakeword_models=[WAKE_MODEL], inference_framework="onnx")


def spoken(text):
    """O texto como deve ser falado: links ficam só na tela."""

    return URL_PATTERN.sub("o link está na tela", text).replace("*", "").strip()


def synthesize(text, voice, rate):
    import edge_tts

    path = Path(tempfile.gettempdir()) / "jarvis_fala.mp3"
    asyncio.run(edge_tts.Communicate(text, voice, rate=rate).save(str(path)))
    return path


def play(path):
    import ctypes

    # O Windows toca MP3 sozinho, sem precisar de outro programa.
    mci = ctypes.windll.winmm.mciSendStringW
    mci(f'open "{path}" type mpegvideo alias jarvis_fala', None, 0, None)
    mci("play jarvis_fala wait", None, 0, None)
    mci("close jarvis_fala", None, 0, None)


class Voice:
    """Conversa por voz numa thread própria.

    on_text(texto) recebe cada frase entendida e responde chamando say().
    on_state(estado) avisa a tela: "idle", "listening", "thinking" ou "speaking".
    """

    def __init__(self, on_text, on_state, preferences):
        self.on_text = on_text
        self.on_state = on_state
        self.voice = preferences["voice"]
        self.rate = preferences["rate"]
        self.wake_word = preferences["wake_word"]
        self.speak_replies = preferences["speak_replies"]
        self.model = None
        # Pede para ouvir agora, sem "Hey Jarvis" (pelo menu do ícone).
        self.trigger = threading.Event()
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            if self.wake_word:
                with microphone() as source:
                    if self.wait_for_wake(source):
                        self.converse(source)

            elif self.trigger.wait(0.5):
                with microphone() as source:
                    self.converse(source)

    def wait_for_wake(self, source):
        """Ouve até "Hey Jarvis" ou um pedido pelo menu. False se a escuta foi desligada."""

        self.model = self.model or wake_model()
        self.model.reset()

        while self.wake_word and not self.stop.is_set():
            if self.trigger.is_set():
                return True

            scores = self.model.predict(read_frame(source))

            if max(scores.values(), default=0) >= WAKE_THRESHOLD:
                return True

        return False

    def converse(self, source):
        import speech_recognition as sr

        self.trigger.clear()
        recognizer = sr.Recognizer()

        while not self.stop.is_set():
            self.on_state("listening")
            text = self.listen(recognizer, source)

            if not text:
                break

            self.on_state("thinking")
            self.on_text(text)

        self.on_state("idle")

    def listen(self, recognizer, source):
        """A próxima frase em texto, ou None se você não falou nada que desse para entender."""

        import speech_recognition as sr

        try:
            audio = recognizer.listen(source, timeout=FOLLOW_UP_TIMEOUT, phrase_time_limit=PHRASE_LIMIT)
            return recognizer.recognize_google(audio, language="pt-BR")

        except (sr.WaitTimeoutError, sr.UnknownValueError):
            return None

        except sr.RequestError:
            self.say("Estou sem acesso ao reconhecimento de voz agora, senhor. Confira a internet.")
            return None

    def say(self, text):
        text = spoken(text)

        if not self.speak_replies or not text:
            return

        self.on_state("speaking")

        try:
            play(synthesize(text, self.voice, self.rate))

        except Exception:
            # Sem internet a voz neural não funciona, mas a resposta continua escrita na tela.
            pass

        finally:
            self.on_state("thinking")
