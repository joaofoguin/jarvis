"""Janela de chat do JARVIS. Rode com: pythonw -m desktop.app (na raiz do projeto)."""

import os
import queue
import threading
import tkinter as tk

import keyboard
import pystray

from PIL import Image, ImageDraw

from desktop import settings
from desktop.core import reply_to
from desktop.voice import Voice


HOTKEY = os.getenv("JARVIS_HOTKEY", "ctrl+alt+j")

# O título da janela mostra o que a voz está fazendo.
VOICE_STATES = {
    "idle": "",
    "listening": " · ouvindo",
    "thinking": " · pensando",
    "speaking": " · falando"
}

# Outras threads (atalho, ícone, IA) só conversam com a janela por esta fila,
# porque o tkinter não pode ser usado fora da thread principal.
events = queue.Queue()


def make_icon_image():
    image = Image.new("RGB", (64, 64), (16, 92, 160))
    ImageDraw.Draw(image).text((26, 22), "J", fill="white")
    return image


class ChatWindow:

    def __init__(self, root):
        self.root = root
        self.history = []

        root.title("JARVIS")
        root.geometry("520x620")
        root.protocol("WM_DELETE_WINDOW", root.withdraw)
        root.bind("<Escape>", lambda event: root.withdraw())

        self.log = tk.Text(root, wrap="word", state="disabled", font=("Segoe UI", 11))
        self.log.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        self.entry = tk.Entry(root, font=("Segoe UI", 11))
        self.entry.pack(fill="x", padx=8, pady=(4, 8))
        self.entry.bind("<Return>", self.send)

        self.write("JARVIS", f"Online, senhor. Use {HOTKEY} para me chamar e Esc para me esconder.")

    def write(self, author, text):
        self.log.configure(state="normal")
        self.log.insert("end", f"{author}: {text}\n\n")
        self.log.configure(state="disabled")
        self.log.see("end")

    def send(self, event=None):
        text = self.entry.get().strip()

        if not text:
            return

        self.entry.delete(0, "end")
        self.write("Você", text)

        threading.Thread(target=self.answer, args=(text, list(self.history)), daemon=True).start()

    def answer(self, text, history, say=None):
        answer, task = reply_to(text, history)
        events.put(("reply", text, answer))

        if say:
            say(answer)

        if task:
            note = task()
            events.put(("note", note))

            if say:
                say(note)

    def answer_aloud(self, voice, text):
        # Roda na thread da voz, que só volta a ouvir depois de responder.
        events.put(("heard", text))
        self.answer(text, list(self.history), say=voice.say)

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.entry.focus_set()

    def toggle(self):
        if self.root.state() == "normal":
            self.root.withdraw()
        else:
            self.show()

    def process_events(self, icon):
        while not events.empty():
            event = events.get()

            if event[0] == "reply":
                _, text, answer = event
                self.write("JARVIS", answer)
                self.history += [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": answer}
                ]

            elif event[0] == "heard":
                self.write("Você", event[1])

            elif event[0] == "state":
                self.root.title("JARVIS" + VOICE_STATES[event[1]])

            elif event[0] == "note":
                self.write("JARVIS", event[1])
                # Guarda o resultado para a IA poder responder perguntas sobre ele depois.
                self.history.append({"role": "assistant", "content": event[1]})

            elif event[0] == "toggle":
                self.toggle()

            elif event[0] == "show":
                self.show()

            elif event[0] == "quit":
                icon.stop()
                self.root.destroy()
                return

        self.root.after(100, self.process_events, icon)


def run_voice(voice):
    try:
        voice.run()

    except Exception as error:
        # Sem microfone ou sem as bibliotecas de voz, o chat por texto continua funcionando.
        events.put(("note", f"Voz desligada: {error}"))


def main():
    root = tk.Tk()
    window = ChatWindow(root)

    voice = Voice(
        on_text=lambda text: window.answer_aloud(voice, text),
        on_state=lambda state: events.put(("state", state)),
        preferences=settings.load()
    )
    threading.Thread(target=run_voice, args=(voice,), daemon=True).start()

    icon = pystray.Icon(
        "jarvis",
        make_icon_image(),
        "JARVIS",
        menu=pystray.Menu(
            pystray.MenuItem("Abrir", lambda: events.put(("show",)), default=True),
            pystray.MenuItem("Falar agora", lambda: voice.trigger.set()),
            pystray.MenuItem("Sair", lambda: events.put(("quit",)))
        )
    )
    icon.run_detached()

    keyboard.add_hotkey(HOTKEY, lambda: events.put(("toggle",)))

    window.process_events(icon)
    root.mainloop()


if __name__ == "__main__":
    main()
