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

import google_data
import updater
from agent import agent
from desktop import connections, dashboard, notices, orb, settings
from desktop.core import reply_to
from desktop.orb import Orb
from desktop.panel import Panel
from desktop.voice import Voice
from router import HISTORY_CONVERSATION, HISTORY_LAST, HISTORY_TODAY, detect_history


HOTKEY = os.getenv("JARVIS_HOTKEY", "ctrl+alt+j")

WEB = Path(__file__).resolve().parent / "web"

# De quanto em quanto tempo o mural do Classroom é consultado, em segundos.
NOTICES_INTERVAL = 300

# Segundos depois de abrir até conferir os logins (Google e iCloud), para não atrasar a abertura.
CONNECTIONS_DELAY = 5

# De quanto em quanto tempo o app procura uma versão nova no GitHub, em segundos.
UPDATES_INTERVAL = 1800

# Pedidos de apagar o histórico, como na Alexa ("apague o que eu acabei de dizer").
FORGET_HISTORY = {
    HISTORY_LAST: dashboard.forget_last,
    HISTORY_CONVERSATION: dashboard.forget_conversation,
    HISTORY_TODAY: dashboard.forget_today
}


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


def check_connections(jarvis, icon):
    """Avisa no chat, logo depois de abrir, se algum login venceu, para não ser pego de surpresa."""

    if jarvis.stopping.wait(CONNECTIONS_DELAY):
        return

    text = updater.report(updater.last_result())
    if text:
        jarvis.write("jarvis", text)

    try:
        working, problems = connections.check()

    except Exception as error:
        print("ERRO AO CONFERIR AS CONEXÕES:", repr(error))
        return

    text = connections.report(working, problems)

    if text:
        jarvis.write("jarvis", text)

    if problems:
        icon.notify("Algum login precisa ser refeito. Veja no chat.", "JARVIS")


def watch_updates(jarvis, icon):
    """Com o app aberto, avisa quando há versão nova no GitHub. Atualizar é pelo ícone, para não cortar uma conversa."""

    warned = 0

    while not jarvis.stopping.wait(UPDATES_INTERVAL):
        try:
            new = updater.behind()

        except Exception as error:
            print("ERRO AO PROCURAR ATUALIZAÇÃO:", repr(error))
            continue

        if new > warned:
            warned = new
            icon.notify("Há uma versão nova. Use \"Atualizar e reiniciar\" neste ícone.", "JARVIS")


def run_agent(jarvis):
    """O agente da fila (Alexa e página /app) roda junto com o app, numa thread própria."""

    lock = agent.start()

    if isinstance(lock, str):
        # Sem AGENT_TOKEN, ou o agente já está aberto em outra janela: o app segue sem ele.
        print("AGENTE DA FILA NÃO INICIADO:", lock)
        return

    agent.serve(lock, jarvis.stopping)


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
        self.stopping = threading.Event()
        self.history = []
        # Voz e chat são a mesma conversa: um "sim" falado vale para a pergunta escrita e vice-versa.
        # A trava faz um pedido terminar de ler e gravar a confirmação pendente antes do outro começar.
        self.turn = threading.Lock()
        self.panel = None
        self.icon = None
        self.voice = Voice(on_text=self.answer_aloud, on_state=self.show_state, preferences=preferences)

    def send(self, text):
        self.write("user", text)
        self.answer(text)

    def talk(self):
        self.voice.toggle()

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

    def delete_conversation(self, start, end):
        # O botão de apagar do feed de conversas.
        self.forget_history(lambda: dashboard.forget_between(start, end))

    def open_item(self, text):
        # Clique num evento ou atividade do painel: abre no Google.
        link = google_data.LINKS.get(text, "")
        if link.startswith("https://"):
            webbrowser.open(link)

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
        try:
            self.reply(text, say)

        except Exception as error:
            # Um erro inesperado não pode derrubar a thread da voz nem deixar o chat sem resposta.
            print("ERRO NA RESPOSTA:", repr(error))
            self.write("jarvis", f"Desculpe, senhor. Algo deu errado: {error}")

    def forget_history(self, forget):
        """Apaga do histórico e esquece a conversa que a IA ainda tinha na memória."""

        with self.turn:
            removed = forget()
            self.history = []

        return removed

    def reply(self, text, say):
        command = detect_history(text)

        if command:
            # Não vai para a IA nem para o histórico: a frase pode ter sido captada sem querer.
            removed = self.forget_history(FORGET_HISTORY[command])
            answer = f"Pronto, senhor. Apaguei {removed} pedido(s) do histórico." if removed else "Não havia nada para apagar, senhor."
            self.write("jarvis", answer)

            if say:
                say(answer)
            return

        with self.turn:
            # As ações executadas entram no histórico junto com o texto, para "tenta de novo" funcionar.
            actions = []
            answer, task = reply_to(text, list(self.history), actions.append)
            self.history += [{"role": "user", "content": text}, *actions, {"role": "assistant", "content": answer}]

        self.write("jarvis", answer)
        dashboard.log(datetime.now(), text, answer)

        if say:
            say(answer)

        if task:
            actions.clear()
            note = task()
            # Guarda o resultado para a IA poder responder perguntas sobre ele depois.
            self.history += [*actions, {"role": "assistant", "content": note}]
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
        jarvis.toggle_fullscreen, jarvis.load_section, jarvis.open_link, jarvis.delete_conversation, jarvis.open_item
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
        jarvis.stopping.set()
        icon.stop()
        jarvis.orb.destroy()
        chat.destroy()
        panel_window.destroy()

    def update_and_restart():
        updater.restart()
        quit_app()

    icon = jarvis.icon = pystray.Icon(
        "jarvis",
        orb.icon(preferences["accent"], 64),
        "JARVIS",
        menu=pystray.Menu(
            pystray.MenuItem("Abrir chat", lambda: jarvis.show_chat(), default=True),
            pystray.MenuItem("Falar agora", lambda: jarvis.talk()),
            pystray.MenuItem("Mostrar ou esconder o orbe", lambda: jarvis.toggle_orb()),
            pystray.MenuItem("Preferências", lambda: jarvis.open_panel()),
            pystray.MenuItem("Atualizar e reiniciar", update_and_restart),
            pystray.MenuItem("Sair", quit_app)
        )
    )
    icon.run_detached()
    threading.Thread(target=watch_notices, args=(jarvis, icon), daemon=True).start()
    threading.Thread(target=run_agent, args=(jarvis,), daemon=True).start()
    threading.Thread(target=check_connections, args=(jarvis, icon), daemon=True).start()
    threading.Thread(target=watch_updates, args=(jarvis, icon), daemon=True).start()

    keyboard.add_hotkey(HOTKEY, jarvis.toggle_chat)

    webview.start(jarvis.start)


if __name__ == "__main__":
    main()
