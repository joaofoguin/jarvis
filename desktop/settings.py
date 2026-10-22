"""Preferências do JARVIS no notebook, guardadas em ~/.jarvis/preferencias.json (fora do Git)."""

import json
import os
import re
from pathlib import Path


# Vozes neurais em português que o painel oferece.
VOICES = {
    "pt-BR-AntonioNeural": "Antônio, masculina",
    "pt-BR-FranciscaNeural": "Francisca, feminina",
    "pt-BR-ThalitaMultilingualNeural": "Thalita, feminina"
}

DEFAULTS = {
    "voice": "pt-BR-AntonioNeural",
    # Velocidade da fala, de "-50%" a "+50%".
    "rate": "+0%",
    # Fica ouvindo "Hey Jarvis" o tempo todo.
    "wake_word": True,
    # Lê em voz alta as respostas às perguntas feitas por voz.
    "speak_replies": True,
    # Cor do orbe e da janela.
    "accent": "#3FD4F5"
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


def save(values):
    """Valida e grava as preferências. Um valor inválido gera ValueError e nada é gravado."""

    preferences = {**load(), **values}

    if preferences["voice"] not in VOICES:
        raise ValueError("voz desconhecida")

    if not re.fullmatch(r"[+-]\d{1,2}%", str(preferences["rate"])) or abs(int(preferences["rate"][:-1])) > 50:
        raise ValueError("velocidade fora de -50% a +50%")

    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(preferences["accent"])):
        raise ValueError("cor inválida")

    for key in ("wake_word", "speak_replies"):
        if not isinstance(preferences[key], bool):
            raise ValueError(f"{key} precisa ser verdadeiro ou falso")

    preferences = {key: preferences[key] for key in DEFAULTS}
    path().parent.mkdir(parents=True, exist_ok=True)
    path().write_text(json.dumps(preferences, indent=2, ensure_ascii=False), encoding="utf-8")

    return preferences
