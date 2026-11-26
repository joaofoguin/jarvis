"""Abre o JARVIS do notebook já atualizado pelo Git. Vira o JARVIS.exe com build_exe.bat.

Ao abrir: puxa as mudanças do GitHub (só avanço rápido, nunca apaga mudanças locais), instala as
bibliotecas se os requirements mudaram e abre o app. O app conta no chat o que foi atualizado.
Só roda comandos fixos de git e pip, nunca texto livre.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


# O .exe fica na pasta do projeto; rodando como script, a pasta é a deste arquivo.
ROOT = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent

GIT_TIMEOUT = 30
PIP_TIMEOUT = 600
REQUIREMENTS = "requirements-desktop.txt"

# Sem abrir janelas de terminal no Windows.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def result_path():
    return Path(os.getenv("JARVIS_UPDATE") or Path.home() / ".jarvis" / "atualizacao.json")


def python(windowless=False):
    """O Python do venv do projeto; sem venv, o do sistema."""

    folder = ROOT / "venv" / ("Scripts" if os.name == "nt" else "bin")
    name = ("pythonw" if windowless else "python") + (".exe" if os.name == "nt" else "")
    return str(folder / name) if (folder / name).exists() else name


def run(*command, timeout=GIT_TIMEOUT):
    done = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW
    )

    if done.returncode != 0:
        lines = (done.stderr or done.stdout).strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f"{command[0]} falhou")

    return done.stdout.strip()


def git(*args):
    return run("git", *args)


def update():
    """Atualiza o projeto. Retorna {"changes": [títulos dos commits novos], "error": texto ou None}."""

    result = {"changes": [], "error": None}

    try:
        before = git("rev-parse", "HEAD")
        git("pull", "--ff-only")
        after = git("rev-parse", "HEAD")

        if before != after:
            result["changes"] = git("log", "--no-merges", "--format=%s", f"{before}..{after}").splitlines()

            changed = git("diff", "--name-only", before, after).splitlines()
            if any(name.startswith("requirements") for name in changed):
                run(python(), "-m", "pip", "install", "-q", "-r", REQUIREMENTS, timeout=PIP_TIMEOUT)

    except Exception as error:
        # Sem internet ou com mudanças locais em conflito: abre a versão que já está no notebook.
        result["error"] = str(error)

    path = result_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def last_result():
    """O resultado da última atualização, uma vez só: depois de lido, é apagado."""

    path = result_path()

    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        path.unlink()
        return result

    except (OSError, ValueError):
        return None


def behind():
    """Quantos commits novos existem no GitHub e ainda não estão no notebook."""

    git("fetch", "--quiet")
    return int(git("rev-list", "--count", "HEAD..@{u}"))


def report(result):
    """Texto para o chat sobre a atualização feita ao abrir, ou None se não houve nada."""

    if not result:
        return None

    if result["error"]:
        return f"Não consegui atualizar pelo GitHub ({result['error']}). Abri a versão que já estava no notebook."

    if result["changes"]:
        return "Atualizado pelo GitHub:\n" + "\n".join(f"- {change}" for change in result["changes"])

    return None


def restart():
    """Abre de novo o JARVIS pelo atualizador. O app atual deve sair logo depois."""

    subprocess.Popen([python(windowless=True), "-m", "updater", "--esperar"], cwd=ROOT, creationflags=NO_WINDOW)


def main():
    if getattr(sys, "frozen", False):
        # O .exe só chama este arquivo pelo Python do projeto; assim, mudanças aqui também chegam pelo Git
        # e o .exe nunca precisa ser refeito.
        subprocess.Popen([python(windowless=True), "-m", "updater"], cwd=ROOT, creationflags=NO_WINDOW)
        return

    if "--esperar" in sys.argv:
        # Dá tempo do app anterior fechar e soltar o agente da fila.
        time.sleep(3)

    update()
    subprocess.Popen([python(windowless=True), "-m", "desktop.app"], cwd=ROOT, creationflags=NO_WINDOW)


if __name__ == "__main__":
    main()
