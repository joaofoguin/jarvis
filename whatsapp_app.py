"""Envia mensagens pelo aplicativo do WhatsApp no Windows (somente na janela de chat).

O app abre a conversa pelo link whatsapp://send com o número e o texto já escrito,
e o JARVIS aperta Enter. O número vem dos contatos do iCloud.
"""

import os
import re
import time
from urllib.parse import quote

import icloud_data


# Tempo máximo para o app abrir e ficar na frente, em segundos.
OPEN_TIMEOUT = 15

# Depois que o app aparece, a conversa ainda leva um instante para carregar o texto.
CHAT_DELAY = 2

# O título da janela do app é só "WhatsApp" (às vezes com as não lidas na frente, "(3) WhatsApp").
# Abas do navegador ("WhatsApp - Microsoft Edge") não contam.
APP_TITLE = re.compile(r"^(\(\d+\) )?WhatsApp$")


def phone_digits(phone):
    """Número só com dígitos e código do país; números sem "+" e com DDD ganham o 55 do Brasil."""

    digits = re.sub(r"\D", "", phone).lstrip("0")

    if not phone.strip().startswith("+") and len(digits) in (10, 11):
        digits = "55" + digits

    return digits


def recipient(contact, cards=None):
    """Retorna (nome, número) de um contato. Para um número digitado, o nome é None."""

    if len(re.sub(r"\D", "", contact)) >= 10:
        return None, phone_digits(contact)

    found = [(name, phones) for name, phones in icloud_data.find_contacts(contact, cards) if phones]

    if not found:
        raise RuntimeError(f"não encontrei {contact} com telefone nos seus contatos do iCloud")

    if len(found) > 1:
        names = ", ".join(name for name, _ in found[:5])
        raise RuntimeError(f"encontrei mais de um contato ({names}); diga o nome completo")

    name, phones = found[0]
    return name, phone_digits(phones[0])


def foreground_title():
    import ctypes

    user32 = ctypes.windll.user32
    window = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(window)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(window, title, length + 1)

    return title.value


def app_in_front():
    return bool(APP_TITLE.match(foreground_title().strip()))


def send(phone, message):
    import keyboard

    os.startfile(f"whatsapp://send?phone={phone}&text={quote(message)}")

    # Só aperta Enter com o WhatsApp na frente, para nunca enviar Enter a outro programa.
    deadline = time.monotonic() + OPEN_TIMEOUT

    while not app_in_front():
        if time.monotonic() > deadline:
            return "Abri a conversa, mas o WhatsApp não ficou na frente, então não apertei Enter. Confira e envie."

        time.sleep(0.5)

    time.sleep(CHAT_DELAY)

    # Confere de novo: na espera, outra janela pode ter ido para a frente.
    if not app_in_front():
        return "Abri a conversa, mas outra janela ficou na frente, então não apertei Enter. Confira e envie."

    keyboard.send("enter")

    return f"Mensagem enviada para +{phone} pelo WhatsApp: \"{message}\""
