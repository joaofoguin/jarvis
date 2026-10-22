"""Preferências do JARVIS no notebook, guardadas em ~/.jarvis/preferencias.json (fora do Git)."""

import json
import os
from pathlib import Path


DEFAULTS = {
    # Vozes neurais em português: pt-BR-AntonioNeural, pt-BR-FranciscaNeural, pt-BR-ThalitaMultilingualNeural.
    "voice": "pt-BR-AntonioNeural",
    # Velocidade da fala, de "-50%" a "+50%".
    "rate": "+0%",
    # Fica ouvindo "Hey Jarvis" o tempo todo.
    "wake_word": True,
    # Lê em voz alta as respostas às perguntas feitas por voz.
    "speak_replies": True
}


def path():
    return Path(os.getenv("JARVIS_SETTINGS") or Path.home() / ".jarvis" / "preferencias.json")


def load():
    """As preferências salvas, com o padrão no lugar do que falta ou não é conhecido."""

    try:
        saved = json.loads(path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        saved = {}

    return {**DEFAULTS, **{key: value for key, value in saved.items() if key in DEFAULTS}}
