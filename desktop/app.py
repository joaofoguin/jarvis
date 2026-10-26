"""JARVIS no notebook: um orbe flutuante, uma janela de chat e o painel de preferências.
Rode com: pythonw -m desktop.app (na raiz do projeto).

Clique no orbe para falar; com o botão direito, o chat abre e fecha. O orbe pode ser arrastado.
"""

import json
import os
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import keyboard
import pystray
import webview

from desktop import dashboard, notices, orb, settings
from desktop.core import reply_to
from desktop.orb import Orb
from desktop.panel import Panel
from desktop.voice import Voice


HOTKEY = os.getenv("JARVIS_HOTKEY", "ctrl+alt+j")

WEB = Path(__file__).resolve().parent / "web"

# De quanto em quanto tempo o mural do Classroom é consultado, em segundos.
NOTICES_INTERVAL = 300


ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)]


def icon_path():
    return Path.home() / ".jarvis" / "jarvis.ico"


def save_icon(accent):
    """Grava o orbe como .ico, na cor escolhida, para as janelas e a barra de tarefas."""

    path = icon_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    orb.icon(accent).save(path, sizes=ICON_SIZES)
    return path


def set_window_icon(window, path):
    # As janelas do pywebview no Windows são formulários do WinForms; o ícone tem que ser trocado na
    # thread delas. Sem isso, a barra de tarefas mostra o ícone do Python.
    from System import Action
    from System.Drawing import Icon

    form = window.native
    form.Invoke(Action(lambda: setattr(form, "Icon", Icon(str(path)))))


def separate_from_python():
    # Um id próprio faz o Windows agrupar as janelas como "JARVIS", com o nosso ícone, e não como Python.
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JARVIS")


def watch_notices(jarvis, icon):
    """Avisa, no chat e com uma notificação do Windows, cada aviso novo no mural do Classroom."""

    while not jarvis.quitting:
        try:
            for course, text in notices.check(dashboard.classroom_accounts()):
                icon.notify(text, f"Classroom: {course}")
                jarvis.write("jarvis", f"Novo aviso em {course}: {text}")

        except Exception as error:
            print("ERRO NOS AVISOS DO CLASSROOM:", repr(error))

        time.sleep(NOTICES_INTERVAL)


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
        self.icon = None
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

        self.orb.set_accent(self.accent)
        call_js(self.chat, "setAccent", self.accent)

        if self.icon:
            self.icon.icon = orb.icon(self.accent, 64)
            self.set_window_icons()

    def set_window_icons(self):
        try:
            path = save_icon(self.accent)
            for window in (self.chat, self.panel.window):
                set_window_icon(window, path)

        except Exception as error:
            # Sem o ícone próprio, as janelas só ficam com o ícone do Python.
            print("ERRO NO ÍCONE DAS JANELAS:", repr(error))

    def toggle_orb(self):
        if self.orb.visible:
            self.orb.hide()
        else:
            self.orb.show()

    def start(self):
        # Roda numa thread própria assim que as janelas abrem.
        call_js(self.chat, "setAccent", self.accent)
        self.set_window_icons()
        self.orb.start(self.talk, self.toggle_chat, lambda error: self.write("jarvis", f"Orbe desligado: {error}"), self.hide_orb)

        self.write("jarvis", f"Online, senhor. Diga \"Hey Jarvis\", clique no orbe ou use {HOTKEY} para o chat.")

        try:
            self.voice.run()

        except Exception as error:
            # Sem microfone ou sem as bibliotecas de voz, o chat por texto continua funcionando.
            self.write("jarvis", f"Voz desligada: {error}")

    def hide_orb(self):
        self.orb.hide()
        if self.icon:
            self.icon.notify("O orbe foi fechado. Para trazê-lo de volta, use \"Mostrar ou esconder o orbe\" neste ícone.", "JARVIS")

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
        self.orb.set_state(state)
        call_js(self.chat, "setState", state)

    def closing(self):
        if self.quitting:
            return True

        # Fechar o chat só esconde a janela; para sair, use o ícone perto do relógio.
        self.hide_chat()
        return False


def main():
    try:
        separate_from_python()

    except Exception as error:
        print("ERRO NO ID DO APP:", repr(error))

    # Sem a barra do Windows: cada tela tem os próprios botões e é arrastada pelo topo.
    chat = webview.create_window(
        "JARVIS", str(WEB / "chat.html"), width=520, height=640, hidden=True,
        frameless=True, easy_drag=False, background_color="#070B12"
    )
    panel_window = webview.create_window(
        "Preferências do JARVIS", str(WEB / "panel.html"), width=980, height=760, hidden=True,
        frameless=True, easy_drag=False, background_color="#070B12"
    )

    preferences = settings.load()
    jarvis = Jarvis(preferences, Orb(preferences["accent"]), chat)
    panel = jarvis.panel = Panel(jarvis, panel_window)
    chat.expose(
        jarvis.send, jarvis.talk, jarvis.hide_chat, jarvis.open_panel,
        jarvis.toggle_fullscreen, jarvis.load_section, jarvis.open_link
    )
    panel_window.expose(
        panel.load_panel, panel.load_usage, panel.save_preferences, panel.preview_voice,
        panel.add_skill_repo, panel.remove_skill_repo, panel.forget_memory, panel.hide_panel,
        panel.connect_notices
    )
    chat.events.closing += jarvis.closing
    panel_window.events.closing += panel.closing

    def quit_app():
        jarvis.quitting = True
        icon.stop()
        jarvis.orb.destroy()
        chat.destroy()
        panel_window.destroy()

    icon = jarvis.icon = pystray.Icon(
        "jarvis",
        orb.icon(preferences["accent"], 64),
        "JARVIS",
        menu=pystray.Menu(
            pystray.MenuItem("Abrir chat", lambda: jarvis.show_chat(), default=True),
            pystray.MenuItem("Falar agora", lambda: jarvis.talk()),
            pystray.MenuItem("Mostrar ou esconder o orbe", lambda: jarvis.toggle_orb()),
            pystray.MenuItem("Preferências", lambda: jarvis.open_panel()),
            pystray.MenuItem("Sair", quit_app)
        )
    )
    icon.run_detached()
    threading.Thread(target=watch_notices, args=(jarvis, icon), daemon=True).start()

    keyboard.add_hotkey(HOTKEY, jarvis.toggle_chat)

    webview.start(jarvis.start)


if __name__ == "__main__":
    main()
