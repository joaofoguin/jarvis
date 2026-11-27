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
# Mais alto = precisa de um "Hey Jarvis" mais claro. 0.5 disparava com conversas em volta.
WAKE_THRESHOLD = 0.7

# Detector de voz humana do openWakeWord: barulho e música não disparam a ativação.
VAD_THRESHOLD = 0.5

# Depois de responder, o JARVIS espera esse tempo (em segundos) por mais uma fala,
# sem precisar de "Hey Jarvis" de novo. Assim dá para conversar.
FOLLOW_UP_TIMEOUT = 6

# Tempo máximo de uma fala, em segundos.
PHRASE_LIMIT = 30

# Silêncio (em segundos) que encerra a frase. O padrão do reconhecedor (0,8 s) cortava
# quem faz uma pausa para pensar no meio do pedido.
PAUSE_THRESHOLD = 1.6

URL_PATTERN = re.compile(r"https?://\S+")

# A fala é gerada em partes: a primeira toca enquanto a próxima é gerada, sem esperar o texto todo.
PART_LIMIT = 180

# Vozes do painel que são uma voz neural com ajuste de tom.
VOICE_PRESETS = {"jarvis": ("pt-BR-AntonioNeural", "-12Hz")}


class Cancelled(Exception):
    """Você clicou de novo no orbe: a escuta para no meio."""


def microphone(cancel=None):
    """O microfone padrão pelo sounddevice, no formato que o SpeechRecognition espera.

    O sounddevice já vem pronto para qualquer versão do Python no Windows, sem compilar nada.
    Com cancel (um threading.Event) ligado, a próxima leitura levanta Cancelled.
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
            if cancel is not None and cancel.is_set():
                raise Cancelled()

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
    return Model(wakeword_models=[WAKE_MODEL], inference_framework="onnx", vad_threshold=VAD_THRESHOLD)


def spoken(text):
    """O texto como deve ser falado: links ficam só na tela. Respostas longas são lidas inteiras, em partes."""

    return URL_PATTERN.sub("o link está na tela", text).replace("*", "").strip()


def parts(text):
    """Divide a fala em frases, juntando as curtas até PART_LIMIT caracteres."""

    result = []

    for sentence in re.split(r"(?<=[.!?:;])\s+|\n+", text):
        sentence = sentence.strip()

        if not sentence:
            continue

        if result and len(result[-1]) + len(sentence) < PART_LIMIT:
            result[-1] += " " + sentence
        else:
            result.append(sentence)

    return result


def synthesize(text, voice, rate, part=0):
    import edge_tts

    name, pitch = VOICE_PRESETS.get(voice, (voice, "+0Hz"))
    path = Path(tempfile.gettempdir()) / f"jarvis_fala_{part}.mp3"
    asyncio.run(edge_tts.Communicate(text, name, rate=rate, pitch=pitch).save(str(path)))
    return path


def play(path, cancel=None):
    import ctypes
    import time

    # O Windows toca MP3 sozinho, sem precisar de outro programa.
    mci = ctypes.windll.winmm.mciSendStringW
    mode = ctypes.create_unicode_buffer(32)
    mci(f'open "{path}" type mpegvideo alias jarvis_fala', None, 0, None)
    mci("play jarvis_fala", None, 0, None)

    # Toca sem travar, para um clique no orbe conseguir parar a fala no meio.
    while not (cancel and cancel.is_set()):
        mci("status jarvis_fala mode", mode, 32, None)
        if mode.value != "playing":
            break
        time.sleep(0.1)

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
        # Um clique durante a conversa liga cancel: para de ouvir ou de falar e encerra a conversa.
        self.cancel = threading.Event()
        self.busy = False
        # Com o orbe fechado, o microfone fica desligado: nem "Hey Jarvis", nem conversa.
        self.paused = False

    def pause(self, paused):
        self.paused = paused

        if paused:
            self.trigger.clear()
            self.cancel.set()

    def toggle(self):
        """O clique no orbe: começa a ouvir ou, se já está numa conversa, cancela."""

        if self.busy:
            self.cancel.set()
        else:
            self.trigger.set()

    def run(self):
        while not self.stop.is_set():
            if self.paused:
                self.stop.wait(0.5)

            elif self.wake_word:
                with microphone(self.cancel) as source:
                    if self.wait_for_wake(source):
                        self.converse(source)

            elif self.trigger.wait(0.5):
                with microphone(self.cancel) as source:
                    self.converse(source)

    def wait_for_wake(self, source):
        """Ouve até "Hey Jarvis" ou um pedido pelo menu. False se a escuta foi desligada."""

        self.model = self.model or wake_model()
        self.model.reset()

        while self.wake_word and not self.paused and not self.stop.is_set():
            if self.trigger.is_set():
                return True

            scores = self.model.predict(read_frame(source))

            if max(scores.values(), default=0) >= WAKE_THRESHOLD:
                return True

        return False

    def converse(self, source):
        import speech_recognition as sr

        self.trigger.clear()
        self.cancel.clear()
        self.busy = True
        recognizer = sr.Recognizer()
        recognizer.pause_threshold = PAUSE_THRESHOLD

        try:
            while not self.stop.is_set() and not self.cancel.is_set():
                self.on_state("listening")
                text = self.listen(recognizer, source)

                if not text or self.cancel.is_set():
                    break

                self.on_state("thinking")
                self.on_text(text)

        finally:
            self.busy = False
            self.cancel.clear()
            self.on_state("idle")

    def listen(self, recognizer, source):
        """A próxima frase em texto, ou None se você não falou nada que desse para entender."""

        import speech_recognition as sr

        try:
            audio = recognizer.listen(source, timeout=FOLLOW_UP_TIMEOUT, phrase_time_limit=PHRASE_LIMIT)
            return recognizer.recognize_google(audio, language="pt-BR")

        except (sr.WaitTimeoutError, sr.UnknownValueError, Cancelled):
            return None

        except sr.RequestError:
            self.say("Estou sem acesso ao reconhecimento de voz agora, senhor. Confira a internet.")
            return None

    def say(self, text):
        text = spoken(text)

        # Cancelado no meio do pedido: a resposta fica só escrita no chat.
        if not self.speak_replies or not text or self.cancel.is_set():
            return

        self.on_state("speaking")

        try:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = [pool.submit(synthesize, part, self.voice, self.rate, index) for index, part in enumerate(parts(text))]

                for future in pending:
                    if self.cancel.is_set():
                        break

                    play(future.result(), self.cancel)

        except Exception:
            # Sem internet a voz neural não funciona, mas a resposta continua escrita na tela.
            pass

        finally:
            self.on_state("thinking")
