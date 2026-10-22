"""Avisos novos no mural do Classroom, para o JARVIS notificar (somente leitura).

O mural pede uma permissão a mais, com login próprio ("mural"), feito uma vez pelo painel.
Assim os logins que já existem para a agenda e as atividades continuam valendo.
"""

import json
import os
from pathlib import Path

import google_data


SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly"
]

KIND = "mural"

# Avisos mais recentes lidos de cada turma em cada consulta.
PAGE_SIZE = 5

TEXT_LIMIT = 200


def seen_path():
    return Path(os.getenv("JARVIS_NOTICES") or Path.home() / ".jarvis" / "avisos_vistos.json")


def connected(account):
    return os.path.exists(google_data.token_file(account, KIND))


def connect(accounts):
    """Faz o login do mural nas contas escolhidas (abre o navegador na primeira vez)."""

    for account in accounts:
        google_data.get_credentials(account, SCOPES, KIND)


def service(account):
    from googleapiclient.discovery import build

    return build("classroom", "v1", credentials=google_data.get_credentials(account, SCOPES, KIND), cache_discovery=False)


def latest(classroom):
    """[(id da turma, turma, quando, texto)] dos avisos mais recentes de cada turma ativa."""

    courses = classroom.courses().list(studentId="me", courseStates=["ACTIVE"]).execute().get("courses", [])
    found = []

    for course in courses:
        items = classroom.courses().announcements().list(
            courseId=course["id"], pageSize=PAGE_SIZE, orderBy="updateTime desc"
        ).execute().get("announcements", [])

        found += [(course["id"], course["name"], item["updateTime"], item.get("text", "")) for item in items]

    return found


def new_since(found, seen):
    """Separa os avisos ainda não vistos. Uma turma nunca vista só é marcada, sem notificar o que já havia."""

    fresh = []
    updated = dict(seen)

    for course_id, course, when, text in found:
        if course_id in seen and when > seen[course_id]:
            fresh.append((course, " ".join(text.split())[:TEXT_LIMIT]))

        updated[course_id] = max(updated.get(course_id, ""), when)

    return fresh, updated


def check(accounts):
    """[(turma, texto)] dos avisos novos desde a última consulta, nas contas já conectadas."""

    path = seen_path()
    seen = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    found = []

    for account in accounts:
        if connected(account):
            found += latest(service(account))

    fresh, seen = new_since(found, seen)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seen), encoding="utf-8")

    return fresh
