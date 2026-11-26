"""Abre e apaga arquivos das pastas do usuário (Downloads, Documentos, Área de Trabalho...), só no notebook.

São ações fixas, como as do agente: nada fora da pasta do usuário nem em pastas do sistema ou ocultas,
nenhum programa ou script é aberto, e apagar manda para a Lixeira depois de um "sim".
"""

import os
from pathlib import Path

from router import normalize


# Abrir um destes executaria código; o JARVIS só abre documentos, páginas e imagens.
BLOCKED = {
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf",
    ".wsh", ".hta", ".lnk", ".reg", ".jar", ".py", ".pyw", ".cpl", ".msc"
}

SKIPPED_FOLDERS = {"node_modules", "venv", "__pycache__", "AppData", "Application Data"}

# Pastas do usuário onde o JARVIS procura. No Windows os nomes são em inglês mesmo com o sistema em português.
USER_FOLDERS = ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "OneDrive"]

# Senhas, chaves e logins nunca são abertos nem apagados pelo JARVIS.
PROTECTED_NAMES = {".env", "credentials.json"}
PROTECTED_PREFIXES = ("google_token",)

# Para a busca não travar numa pasta enorme.
MAX_SCANNED = 200_000


def roots():
    """As pastas onde o JARVIS pode mexer: as do usuário e a pasta de trabalho do Claude Code."""

    folders = [Path.home() / name for name in USER_FOLDERS]
    workspace = os.getenv("JARVIS_WORKSPACE")

    if workspace:
        folders.append(Path(workspace))

    found = []

    for folder in folders:
        folder = folder.resolve()
        if folder.is_dir() and not any(folder.is_relative_to(other) or other.is_relative_to(folder) for other in found):
            found.append(folder)

    return found


def allowed(path):
    path = path.resolve()
    inside = [root for root in roots() if path.is_relative_to(root)]

    if not inside or path.name.lower() in PROTECTED_NAMES or path.name.lower().startswith(PROTECTED_PREFIXES):
        return False

    # Pastas ocultas (.ssh, .git, .jarvis) e do sistema ficam de fora.
    parts = path.relative_to(inside[0]).parts
    return not any(part.startswith(".") or part in SKIPPED_FOLDERS for part in parts)


def relative(path):
    try:
        return str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def find(name):
    """O arquivo com esse nome (ou parte dele) nas pastas do usuário; se houver vários, o mais recente."""

    wanted = normalize(Path(str(name).strip()).name)

    if not wanted:
        raise RuntimeError("diga o nome do arquivo")

    found = []
    scanned = 0

    for root in roots():
        for folder, folders, files in os.walk(root):
            folders[:] = [item for item in folders if not item.startswith(".") and item not in SKIPPED_FOLDERS]
            scanned += len(files)
            found += [Path(folder, file) for file in files if wanted in normalize(file)]

            if scanned > MAX_SCANNED:
                break

    # Atalhos e links simbólicos podem apontar para fora das pastas permitidas.
    found = [path for path in found if allowed(path)]

    if not found:
        raise RuntimeError(f"não achei \"{name}\" nas suas pastas (Downloads, Documentos, Área de Trabalho...)")

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
