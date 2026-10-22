"""JARVIS no notebook: um orbe flutuante, uma janela de chat e o painel de preferências.
Rode com: pythonw -m desktop.app (na raiz do projeto).

Clique no orbe para falar; com o botão direito, o chat abre e fecha. O orbe pode ser arrastado.
"""

import json
import os
import webbrowser
from datetime import datetime
from pathlib import Path

import keyboard
import pystray
import webview

from PIL import Image, ImageDraw

from desktop import dashboard, settings
from desktop.core import reply_to
from desktop.panel import Panel
from desktop.voice import Voice


HOTKEY = os.getenv("JARVIS_HOTKEY", "ctrl+alt+j")

WEB = Path(__file__).resolve().parent / "web"

ORB_SIZE = 160

# Distância do orbe até o canto inferior direito da tela.
ORB_MARGIN = 40

# Cor que o Windows deixa invisível atrás do orbe. Quase preta, para as bordas do brilho não destoarem.
TRANSPARENT_KEY = (1, 2, 3)


def make_icon_image():
    image = Image.new("RGB", (64, 64), (16, 92, 160))
    ImageDraw.Draw(image).text((26, 22), "J", fill="white")
    return image


def clear_background(window):
    """Tira o fundo cinza que o Windows pinta atrás de uma janela transparente do WebView2."""

    from System import Func, Type
    from System.Drawing import Color

    form = window.native
    key = Color.FromArgb(*TRANSPARENT_KEY)

    def apply():
        form.BackColor = key
        form.TransparencyKey = key

    form.Invoke(Func[Type](apply))


def call_js(window, function, *args):
    # json.dumps deixa qualquer texto seguro como argumento de JavaScript.
    window.evaluate_js(f"{function}({', '.join(json.dumps(arg) for arg in args)})")


class Jarvis:
    """Liga a voz, o orbe e o chat. Os métodos expostos em main() são chamados pelo JavaScript das janelas."""

    def __init__(self, preferences, orb, chat):
        self.accent = preferences["accent"]
        self.orb = orb
        self.chat = chat
        self.chat_visible = False
        self.quitting = False
        self.history = []
        self.panel = None
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

    def toggle_fullscreen(self):
        self.chat.toggle_fullscreen()

    def load_section(self, name):
        return dashboard.load(name)

    def open_link(self, url):
        # Só links da web, abertos no navegador padrão.
        if url.startswith("https://"):
            webbrowser.open(url)

    def open_panel(self):
        self.panel.show()

    def apply_preferences(self, preferences):
        # Vale na hora, sem reiniciar o app.
        self.accent = preferences["accent"]
        self.voice.voice = preferences["voice"]
        self.voice.rate = preferences["rate"]
        self.voice.wake_word = preferences["wake_word"]
        self.voice.speak_replies = preferences["speak_replies"]

        for window in (self.orb, self.chat):
            call_js(window, "setAccent", self.accent)

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
        dashboard.log(datetime.now(), text, answer)

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
    # Sem a barra do Windows: cada tela tem os próprios botões e é arrastada pelo topo.
    chat = webview.create_window(
        "JARVIS", str(WEB / "chat.html"), width=520, height=640, hidden=True,
        frameless=True, easy_drag=False, background_color="#070B12"
    )
    panel_window = webview.create_window(
        "Preferências do JARVIS", str(WEB / "panel.html"), width=980, height=760, hidden=True,
        frameless=True, easy_drag=False, background_color="#070B12"
    )

    jarvis = Jarvis(settings.load(), orb, chat)
    panel = jarvis.panel = Panel(jarvis, panel_window)
    orb.expose(jarvis.talk, jarvis.toggle_chat)
    chat.expose(
        jarvis.send, jarvis.talk, jarvis.hide_chat, jarvis.open_panel,
        jarvis.toggle_fullscreen, jarvis.load_section, jarvis.open_link
    )
    panel_window.expose(
        panel.load_panel, panel.load_usage, panel.save_preferences, panel.preview_voice,
        panel.add_skill_repo, panel.remove_skill_repo, panel.forget_memory, panel.hide_panel
    )
    orb.events.loaded += lambda: clear_background(orb)
    chat.events.closing += jarvis.closing
    panel_window.events.closing += panel.closing

    def quit_app():
        jarvis.quitting = True
        icon.stop()
        orb.destroy()
        chat.destroy()
        panel_window.destroy()

    icon = pystray.Icon(
        "jarvis",
        make_icon_image(),
        "JARVIS",
        menu=pystray.Menu(
            pystray.MenuItem("Abrir chat", lambda: jarvis.show_chat(), default=True),
            pystray.MenuItem("Falar agora", lambda: jarvis.talk()),
            pystray.MenuItem("Preferências", lambda: jarvis.open_panel()),
            pystray.MenuItem("Sair", quit_app)
        )
    )
    icon.run_detached()

    keyboard.add_hotkey(HOTKEY, jarvis.toggle_chat)

    webview.start(jarvis.start)


if __name__ == "__main__":
    main()
