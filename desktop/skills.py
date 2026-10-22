"""Repositórios de Skills do GitHub para as tarefas do Claude Code.

Cada repositório é baixado em ~/.jarvis/skills e as pastas com SKILL.md são copiadas para
JARVIS_WORKSPACE/.claude/skills, onde o Claude Code as encontra.
"""

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path


REPO_PATTERN = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?")

CLONE_TIMEOUT = 120


def folder():
    return Path(os.getenv("JARVIS_SKILLS") or Path.home() / ".jarvis" / "skills")


def target():
    workspace = os.getenv("JARVIS_WORKSPACE")

    if not workspace or not os.path.isdir(workspace):
        raise RuntimeError("JARVIS_WORKSPACE não configurado ou a pasta não existe")

    return Path(workspace) / ".claude" / "skills"


def installed():
    """{"dono/repositorio": [skills]} do que já foi adicionado."""

    path = folder() / "instalados.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_installed(repos):
    folder().mkdir(parents=True, exist_ok=True)
    (folder() / "instalados.json").write_text(json.dumps(repos, indent=2), encoding="utf-8")


def delete(path):
    # No Windows os arquivos do Git são somente leitura; libera antes de apagar.
    def writable(function, failed, error):
        os.chmod(failed, stat.S_IWRITE)
        function(failed)

    if path.exists():
        shutil.rmtree(path, onexc=writable)


def repo_name(url):
    match = REPO_PATTERN.fullmatch(url.strip())

    if not match or match.group(2) in (".", ".."):
        raise ValueError("use um endereço como https://github.com/dono/repositorio")

    return f"{match.group(1)}/{match.group(2)}"


def clone(url, destination):
    git = shutil.which("git")

    if not git:
        raise RuntimeError("o Git não está instalado")

    # Lista de argumentos, sem terminal: o endereço já foi validado e nunca vira comando.
    subprocess.run([git, "clone", "--depth", "1", url, str(destination)], check=True, capture_output=True, timeout=CLONE_TIMEOUT)


def add(url):
    name = repo_name(url)
    repos = installed()

    if name in repos:
        raise ValueError(f"{name} já foi adicionado")

    skills_dir = target()
    clone_dir = folder() / name.replace("/", "__")
    delete(clone_dir)
    clone(f"https://github.com/{name}", clone_dir)

    found = [path.parent for path in clone_dir.rglob("SKILL.md") if ".git" not in path.parts]
    # Nunca substitui uma skill que já está na pasta, seja de outro repositório ou sua.
    conflicts = [path.name for path in found if (skills_dir / path.name).exists()]

    if not found or conflicts:
        delete(clone_dir)
        raise ValueError(f"já existe uma skill com o nome {', '.join(conflicts)}" if conflicts else "esse repositório não tem nenhuma skill (SKILL.md)")

    for path in found:
        shutil.copytree(path, skills_dir / path.name, ignore=shutil.ignore_patterns(".git"))

    repos[name] = sorted(path.name for path in found)
    save_installed(repos)

    return repos[name]


def remove(name):
    repos = installed()

    if name not in repos:
        raise ValueError(f"{name} não está na lista")

    for skill in repos.pop(name):
        delete(target() / skill)

    delete(folder() / name.replace("/", "__"))
    save_installed(repos)
