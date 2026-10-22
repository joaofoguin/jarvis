import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture(autouse=True)
def isolated_memory(monkeypatch, tmp_path):
    # Os testes nunca leem nem escrevem a memória real do JARVIS.
    monkeypatch.setenv("JARVIS_MEMORY", str(tmp_path / "memoria"))
    monkeypatch.delenv("WHATSAPP_APELIDOS", raising=False)
