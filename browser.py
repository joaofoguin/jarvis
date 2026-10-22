"""Instagram pelo navegador, com um perfil só do JARVIS (somente na janela de chat).

O login é feito uma vez no próprio navegador que o JARVIS abre e fica salvo no perfil, fora do Git.
"""

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path


DEFAULT_PROFILE = str(Path.home() / ".jarvis" / "navegador")

# Tempo para você entrar no Instagram, em milissegundos.
LOGIN_TIMEOUT = 120_000

INSTAGRAM_INBOX = "https://www.instagram.com/direct/inbox/"

# Identificador público que o próprio site do Instagram envia nas suas chamadas.
INSTAGRAM_APP_ID = "936619743392459"

# O perfil só pode ser aberto por uma ação de cada vez.
lock = threading.Lock()


@contextmanager
def browser_page(url):
    from playwright.sync_api import sync_playwright

    # Lido na hora de abrir, porque o .env só é carregado depois que este módulo é importado.
    profile = os.getenv("JARVIS_BROWSER_PROFILE", DEFAULT_PROFILE)

    # O Edge já vem no Windows, então não é preciso baixar outro navegador.
    channel = os.getenv("JARVIS_BROWSER", "msedge") or None

    with lock, sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(profile, channel=channel, headless=False)

        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url)
            yield page

        finally:
            context.close()


def instagram_unread():
    with browser_page(INSTAGRAM_INBOX) as page:
        if not instagram_logged_in(page):
            wait_instagram_login(page)
            page.goto(INSTAGRAM_INBOX)

        # Lê a caixa de entrada pela mesma chamada que o site faz, já com o seu login.
        data = page.evaluate(
            """async (appId) => {
                const response = await fetch('/api/v1/direct_v2/inbox/?limit=20&thread_message_limit=20', {
                    headers: {'X-IG-App-ID': appId},
                    credentials: 'include'
                });
                return response.json();
            }""",
            INSTAGRAM_APP_ID
        )

    return unread_summary(data)


def instagram_logged_in(page):
    return any(cookie["name"] == "sessionid" for cookie in page.context.cookies("https://www.instagram.com"))


def wait_instagram_login(page):
    deadline = time.monotonic() + LOGIN_TIMEOUT / 1000

    while not instagram_logged_in(page):
        if time.monotonic() > deadline:
            raise RuntimeError("o login no Instagram não foi concluído a tempo")

        page.wait_for_timeout(1000)


def unread_summary(data):
    if "inbox" not in data:
        raise RuntimeError(data.get("message") or "o Instagram não devolveu a caixa de entrada")

    people = []

    for thread in data["inbox"].get("threads", []):
        viewer = str(thread.get("viewer_id"))
        seen = int(thread.get("last_seen_at", {}).get(viewer, {}).get("timestamp", 0))

        new = [
            item for item in thread.get("items", [])
            if str(item.get("user_id")) != viewer and int(item.get("timestamp", 0)) > seen
        ]

        if new:
            users = thread.get("users", [])
            name = thread.get("thread_title") or (users[0].get("username") if users else "alguém")
            people.append((name, len(new)))

    if not people:
        return "Nenhuma mensagem nova no Instagram, senhor."

    lines = ["Mensagens novas no Instagram:"]
    lines += [f"- {name}: {count} {'mensagem' if count == 1 else 'mensagens'}" for name, count in people]

    return "\n".join(lines)
