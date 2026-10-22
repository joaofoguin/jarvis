"""WhatsApp Web e Instagram pelo navegador, com um perfil só do JARVIS (somente na janela de chat).

O login é feito uma vez no próprio navegador que o JARVIS abre (QR code no WhatsApp,
senha no Instagram) e fica salvo no perfil, fora do Git.
"""

import os
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from router import normalize


DEFAULT_PROFILE = str(Path.home() / ".jarvis" / "navegador")

# Tempo para você escanear o QR code ou entrar no Instagram, em milissegundos.
LOGIN_TIMEOUT = 120_000
WAIT = 30_000

MAX_CHATS = 20

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


def contact_name(name):
    """Troca um apelido de WHATSAPP_APELIDOS (ex.: "namorada:Amor") pelo nome salvo no WhatsApp."""

    text = normalize(name)

    for pair in os.getenv("WHATSAPP_APELIDOS", "").split(","):
        alias, _, contact = pair.partition(":")

        if alias.strip() and contact.strip() and re.search(rf"\b{re.escape(normalize(alias))}\b", text):
            return contact.strip()

    return name.strip()


def whatsapp_send(contact, message):
    with browser_page("https://web.whatsapp.com") as page:
        # Na primeira vez aparece o QR code; a lista de conversas só surge depois do login.
        page.wait_for_selector("#pane-side", timeout=LOGIN_TIMEOUT)

        page.locator("#side [contenteditable='true'], #side input").first.click()
        page.keyboard.type(contact)
        page.wait_for_timeout(2000)

        chats = chat_names(page)
        wanted = [(index, name) for index, name in chats if normalize(name) == normalize(contact)]

        if not wanted:
            found = ", ".join(dict.fromkeys(name for _, name in chats))
            return f"Não encontrei {contact} no WhatsApp." + (f" Encontrei: {found}." if found else "")

        index, contact = wanted[0]
        chat_rows(page).nth(index).click()

        box = page.locator("#main footer [contenteditable='true']").first
        box.wait_for(timeout=WAIT)
        box.click()
        page.keyboard.type(message)
        page.keyboard.press("Enter")

        # O relógio some quando a mensagem sai; fechar o navegador antes disso cancelaria o envio.
        try:
            page.wait_for_timeout(1000)
            page.locator('#main [data-icon="msg-time"]').first.wait_for(state="detached", timeout=WAIT)

        except Exception:
            return f"Escrevi a mensagem para {contact}, mas não consegui confirmar o envio. Confira no celular."

    return f"Mensagem enviada para {contact} no WhatsApp: \"{message}\""


def chat_rows(page):
    return page.locator("#pane-side [role='listitem'], #pane-side [role='row']")


def chat_names(page):
    """[(posição, nome)] das conversas listadas. O primeiro título de cada linha é o nome do contato."""

    rows = chat_rows(page)
    names = []

    for index in range(min(rows.count(), MAX_CHATS)):
        title = rows.nth(index).locator("span[title]").first

        if title.count():
            names.append((index, title.get_attribute("title") or ""))

    return names


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
