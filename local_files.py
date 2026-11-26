"""Abre e apaga arquivos da pasta de trabalho do JARVIS (JARVIS_WORKSPACE), só no notebook.

São ações fixas, como as do agente: nada fora da pasta, nenhum programa ou script é aberto,
e apagar manda para a Lixeira depois de um "sim".
"""

import os
from pathlib import Path

from router import normalize


# Abrir um destes executaria código; o JARVIS só abre documentos, páginas e imagens.
BLOCKED = {
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf",
    ".wsh", ".hta", ".lnk", ".reg", ".jar", ".py", ".pyw", ".cpl", ".msc"
}

SKIPPED_FOLDERS = {".git", "node_modules", "venv", ".venv", "__pycache__"}


def workspace():
    folder = os.getenv("JARVIS_WORKSPACE")

    if not folder or not os.path.isdir(folder):
        raise RuntimeError("a pasta de trabalho (JARVIS_WORKSPACE) não está configurada no .env")

    return Path(folder).resolve()


def relative(path):
    return str(path.relative_to(workspace()))


def find(name):
    """O arquivo da pasta de trabalho com esse nome (ou parte dele); se houver vários, o mais recente."""

    root = workspace()
    wanted = normalize(Path(str(name).strip()).name)

    if not wanted:
        raise RuntimeError("diga o nome do arquivo")

    found = []

    for folder, folders, files in os.walk(root):
        folders[:] = [item for item in folders if item not in SKIPPED_FOLDERS]
        found += [Path(folder, file) for file in files if wanted in normalize(file)]

    # Atalhos e links simbólicos podem apontar para fora da pasta.
    found = [path for path in found if path.resolve().is_relative_to(root)]

    if not found:
        raise RuntimeError(f"não achei \"{name}\" na pasta de trabalho")

    exact = [path for path in found if normalize(path.name) == wanted]
    return max(exact or found, key=lambda path: path.stat().st_mtime)


def open_file(path):
    if path.suffix.lower() in BLOCKED:
        return f"Não abro {path.name}, senhor: é um programa ou script. Abra você mesmo se confiar nele."

    os.startfile(path)
    return f"Abri {relative(path)}, senhor."


def delete(path):
    from send2trash import send2trash

    send2trash(str(path))
    return f"Apaguei {path.name}, senhor. Ele está na Lixeira, se precisar recuperar."
