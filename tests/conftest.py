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

    # Nem as contas reais: sem as variáveis do .env e fora da pasta do projeto, onde ficam
    # credentials.json e os google_token*.json. Assim nenhum teste chega ao Google, ao iCloud,
    # ao Neon ou ao DeepSeek, mesmo no notebook já configurado.
    for name in (
        "ICLOUD_EMAIL", "ICLOUD_APP_PASSWORD", "GOOGLE_ACCOUNTS", "YOUTUBE_ACCOUNT", "POSTGRES_URL",
        "DEEPSEEK_API_KEY", "AGENT_TOKEN", "JARVIS_API_TOKEN", "JARVIS_WORKSPACE", "JARVIS_URL"
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("JARVIS_DOWNLOADS", str(tmp_path / "downloads"))
    monkeypatch.chdir(tmp_path)
