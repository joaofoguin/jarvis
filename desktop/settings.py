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
    "accent": "#3FD4F5",
    # Temas das notícias do painel em tela cheia.
    "news_topics": ["tecnologia", "inteligência artificial"],
    # Contas do Classroom no painel e nos avisos do mural. Vazio = todas as de GOOGLE_ACCOUNTS.
    "classroom_accounts": []
}

MAX_TOPICS = 10
MAX_TOPIC_LENGTH = 60


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

    topics = preferences["news_topics"]

    if not isinstance(topics, list) or len(topics) > MAX_TOPICS:
        raise ValueError(f"use até {MAX_TOPICS} temas de notícias")

    topics = [" ".join(str(topic).split()) for topic in topics]

    if any(not topic or len(topic) > MAX_TOPIC_LENGTH for topic in topics):
        raise ValueError(f"cada tema de notícias precisa ter de 1 a {MAX_TOPIC_LENGTH} letras")

    preferences["news_topics"] = list(dict.fromkeys(topics))

    if not isinstance(preferences["classroom_accounts"], list) or not all(
        isinstance(account, str) and "@" in account for account in preferences["classroom_accounts"]
    ):
        raise ValueError("escolha as contas do Classroom pela lista")

    preferences = {key: preferences[key] for key in DEFAULTS}
    path().parent.mkdir(parents=True, exist_ok=True)
    path().write_text(json.dumps(preferences, indent=2, ensure_ascii=False), encoding="utf-8")

    return preferences
