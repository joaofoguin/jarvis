import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture(autouse=True)
def isolated_memory(monkeypatch, tmp_path):
    # Os testes nunca leem nem escrevem a memória real do JARVIS.
    monkeypatch.setenv("JARVIS_MEMORY", str(tmp_path / "memoria"))
    monkeypatch.delenv("WHATSAPP_APELIDOS", raising=False)
    monkeypatch.setenv("JARVIS_SETTINGS", str(tmp_path / "preferencias.json"))
    monkeypatch.setenv("JARVIS_SKILLS", str(tmp_path / "skills"))
    monkeypatch.setenv("JARVIS_HISTORY", str(tmp_path / "historico.jsonl"))
    monkeypatch.setenv("JARVIS_NOTICES", str(tmp_path / "avisos_vistos.json"))

    # O .env do notebook é carregado ao importar o agente; sem isto, um teste poderia usar
    # as chaves reais (iCloud, DeepSeek, banco). Cada teste que precisa de uma define a sua.
    for name in [
        "DEEPSEEK_API_KEY", "POSTGRES_URL", "AGENT_TOKEN", "JARVIS_API_TOKEN", "ICLOUD_EMAIL", "ICLOUD_APP_PASSWORD",
        "GOOGLE_ACCOUNTS", "YOUTUBE_ACCOUNT", "JARVIS_WORKSPACE", "JARVIS_BROWSER"
    ]:
        monkeypatch.delenv(name, raising=False)
