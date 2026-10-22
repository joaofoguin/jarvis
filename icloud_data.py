"""Contatos e calendário do iPhone, lidos do iCloud para a janela de chat (somente leitura).

Usa uma senha de app da Apple (account.apple.com → Senhas de app), nunca a senha da conta.
"""

import os
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests

from router import normalize


CALDAV_URL = "https://caldav.icloud.com"
CARDDAV_URL = "https://contacts.icloud.com"

MAX_ITEMS = 10
MAX_CONTACTS = 5

NS = {"d": "DAV:", "card": "urn:ietf:params:xml:ns:carddav"}

PRINCIPAL_BODY = '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'

HOME_BODY = (
    '<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><card:addressbook-home-set/></d:prop></d:propfind>"
)

BOOKS_BODY = '<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'

# Todo contato tem FN (nome de exibição), então o filtro traz todos.
CARDS_BODY = (
    '<card:addressbook-query xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><card:address-data/></d:prop>"
    '<card:filter><card:prop-filter name="FN"/></card:filter>'
    "</card:addressbook-query>"
)


def configured():
    return bool(os.getenv("ICLOUD_EMAIL") and os.getenv("ICLOUD_APP_PASSWORD"))


def credentials():
    if not configured():
        raise RuntimeError("Coloque ICLOUD_EMAIL e ICLOUD_APP_PASSWORD no .env. Veja o guia do iPhone.")

    return os.getenv("ICLOUD_EMAIL"), os.getenv("ICLOUD_APP_PASSWORD")


def carddav(method, url, body, depth):
    response = requests.request(
        method,
        url,
        data=body,
        headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
        auth=credentials(),
        timeout=20
    )

    if response.status_code == 401:
        raise RuntimeError("o iCloud recusou o login; confira ICLOUD_EMAIL e a senha de app")

    response.raise_for_status()

    return ElementTree.fromstring(response.content)


def address_cards():
    """Retorna o texto (vCard) de todos os contatos do iCloud."""

    root = carddav("PROPFIND", CARDDAV_URL, PRINCIPAL_BODY, "0")
    principal = urljoin(CARDDAV_URL, root.find(".//d:current-user-principal/d:href", NS).text)

    root = carddav("PROPFIND", principal, HOME_BODY, "0")
    home = urljoin(principal, root.find(".//card:addressbook-home-set/d:href", NS).text)

    root = carddav("PROPFIND", home, BOOKS_BODY, "1")
    books = [
        urljoin(home, response.find("d:href", NS).text)
        for response in root.findall("d:response", NS)
        if response.find(".//d:resourcetype/card:addressbook", NS) is not None
    ]

    cards = []

    for book in books:
        root = carddav("REPORT", book, CARDS_BODY, "1")
        cards += [item.text for item in root.iter("{urn:ietf:params:xml:ns:carddav}address-data") if item.text]

    return cards


def parse_card(text):
    """Retorna (nome, [telefones]) de um vCard."""

    # Linhas longas do vCard continuam na linha seguinte, começando com espaço.
    lines = re.sub(r"\r?\n[ \t]", "", text).splitlines()
    name = ""
    phones = []

    for line in lines:
        key, _, value = line.partition(":")
        field = key.split(";")[0].split(".")[-1].upper()

        if field == "FN":
            name = value.replace("\\,", ",").strip()

        elif field == "TEL":
            phones.append(value.removeprefix("tel:").strip())

    return name, phones


def find_contacts(name, cards=None):
    """Contatos cujo nome contém o texto pedido; o nome exato vem primeiro."""

    wanted = normalize(name)
    contacts = [parse_card(card) for card in (address_cards() if cards is None else cards)]
    found = [contact for contact in contacts if wanted and wanted in normalize(contact[0])]

    return sorted(found, key=lambda contact: normalize(contact[0]) != wanted)


def contact_summary(name, cards=None):
    found = find_contacts(name, cards)

    if not found:
        return f"Não encontrei {name} nos seus contatos do iCloud, senhor."

    lines = [
        f"- {contact}: {', '.join(phones) if phones else 'sem telefone'}"
        for contact, phones in found[:MAX_CONTACTS]
    ]

    return "\n".join(["Contatos encontrados:"] + lines)


def calendars():
    import caldav

    email, password = credentials()
    return caldav.DAVClient(url=CALDAV_URL, username=email, password=password).principal().calendars()


def agenda_summary(days, calendar_list=None):
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)

    events = []
    errors = []

    for calendar in calendars() if calendar_list is None else calendar_list:
        try:
            found = calendar.search(start=start, end=end, event=True, expand=True)

        except Exception as error:
            errors.append(f"Não consegui ler o calendário {calendar.name} do iCloud: {str(error)[:200]}")
            continue

        for event in found:
            component = event.icalendar_component
            events.append(format_event(component["dtstart"].dt, str(component.get("summary", "(sem título)"))))

    period = "hoje" if days == 1 else f"nos próximos {days} dias"

    if events:
        events.sort(key=lambda entry: entry[0])
        lines = [f"Calendário do iCloud {period}:"] + [f"- {text}" for _, text in events[:MAX_ITEMS]]
    elif not errors:
        lines = [f"Nada no calendário do iCloud {period}, senhor."]
    else:
        lines = []

    return "\n".join(lines + errors)


def format_event(start, title):
    # Eventos de dia inteiro só têm a data.
    if not isinstance(start, datetime):
        return datetime.combine(start, datetime.min.time()).astimezone(), f"{start:%d/%m} (dia todo) {title}"

    start = start.astimezone()
    return start, f"{start:%d/%m %H:%M} {title}"
