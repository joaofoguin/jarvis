"""JARVIS no notebook: um orbe flutuante e uma janela de chat. Rode com: pythonw -m desktop.app (na raiz do projeto).

Clique no orbe para falar; com o botão direito, o chat abre e fecha. O orbe pode ser arrastado.
"""

import json
import os
import threading
from pathlib import Path

import keyboard
import pystray
import webview

from PIL import Image, ImageDraw

from desktop import settings
from desktop.core import reply_to
from desktop.voice import Voice


HOTKEY = os.getenv("JARVIS_HOTKEY", "ctrl+alt+j")

WEB = Path(__file__).resolve().parent / "web"

ORB_SIZE = 160

# Distância do orbe até o canto inferior direito da tela.
ORB_MARGIN = 40


def make_icon_image():
    image = Image.new("RGB", (64, 64), (16, 92, 160))
    ImageDraw.Draw(image).text((26, 22), "J", fill="white")
    return image


def call_js(window, function, *args):
    # json.dumps deixa qualquer texto seguro como argumento de JavaScript.
    window.evaluate_js(f"{function}({', '.join(json.dumps(arg) for arg in args)})")


class Jarvis:
    """Liga a voz, o orbe e o chat. send, talk, toggle_chat e hide_chat são chamados pelo JavaScript das janelas."""

    def __init__(self, preferences, orb, chat):
        self.accent = preferences["accent"]
        self.orb = orb
        self.chat = chat
        self.chat_visible = False
        self.quitting = False
        self.history = []
        self.voice = Voice(on_text=self.answer_aloud, on_state=self.show_state, preferences=preferences)

    def send(self, text):
        self.write("user", text)
        self.answer(text)

    def talk(self):
        self.voice.trigger.set()

    def toggle_chat(self):
        if self.chat_visible:
            self.hide_chat()
        else:
            self.show_chat()

    def hide_chat(self):
        self.chat_visible = False
        self.chat.hide()

    def show_chat(self):
        self.chat_visible = True
        self.chat.show()
        call_js(self.chat, "focusInput")

    def start(self):
        # Roda numa thread própria assim que as janelas abrem.
        for window in (self.orb, self.chat):
            call_js(window, "setAccent", self.accent)

        self.write("jarvis", f"Online, senhor. Diga \"Hey Jarvis\", clique no orbe ou use {HOTKEY} para o chat.")

        try:
            self.voice.run()

        except Exception as error:
            # Sem microfone ou sem as bibliotecas de voz, o chat por texto continua funcionando.
            self.write("jarvis", f"Voz desligada: {error}")

    def answer_aloud(self, text):
        # Roda na thread da voz, que só volta a ouvir depois de responder.
        self.write("user", text)
        self.answer(text, say=self.voice.say)

    def answer(self, text, say=None):
        answer, task = reply_to(text, list(self.history))
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
        self.write("jarvis", answer)

        if say:
            say(answer)

        if task:
            note = task()
            # Guarda o resultado para a IA poder responder perguntas sobre ele depois.
            self.history.append({"role": "assistant", "content": note})
            self.write("jarvis", note)

            if say:
                say(note)

    def write(self, author, text):
        call_js(self.chat, "addMessage", author, text)

    def show_state(self, state):
        for window in (self.orb, self.chat):
            call_js(window, "setState", state)

    def closing(self):
        if self.quitting:
            return True

        # Fechar o chat só esconde a janela; para sair, use o ícone perto do relógio.
        self.hide_chat()
        return False


def main():
    screen = webview.screens[0]

    orb = webview.create_window(
        "JARVIS",
        str(WEB / "orb.html"),
        width=ORB_SIZE,
        height=ORB_SIZE,
        x=screen.width - ORB_SIZE - ORB_MARGIN,
        y=screen.height - ORB_SIZE - ORB_MARGIN * 2,
        frameless=True,
        transparent=True,
        on_top=True,
        resizable=False,
        shadow=False
    )
    chat = webview.create_window("JARVIS", str(WEB / "chat.html"), width=520, height=640, hidden=True, background_color="#070B12")

    jarvis = Jarvis(settings.load(), orb, chat)
    orb.expose(jarvis.talk, jarvis.toggle_chat)
    chat.expose(jarvis.send, jarvis.talk, jarvis.hide_chat)
    chat.events.closing += jarvis.closing

    def quit_app():
        jarvis.quitting = True
        icon.stop()
        orb.destroy()
        chat.destroy()

    icon = pystray.Icon(
        "jarvis",
        make_icon_image(),
        "JARVIS",
        menu=pystray.Menu(
            pystray.MenuItem("Abrir chat", lambda: jarvis.show_chat(), default=True),
            pystray.MenuItem("Falar agora", lambda: jarvis.talk()),
            pystray.MenuItem("Sair", quit_app)
        )
    )
    icon.run_detached()

    keyboard.add_hotkey(HOTKEY, jarvis.toggle_chat)

    webview.start(jarvis.start)


if __name__ == "__main__":
    main()
