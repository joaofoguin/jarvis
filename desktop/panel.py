"""Painel de preferências: os métodos públicos são chamados pelo JavaScript de web/panel.html.

Cada um devolve {"ok": dados} ou {"error": mensagem}, para o painel mostrar o problema sem travar.
"""

import google_data
import memory

from desktop import dashboard, notices, settings, skills, usage, voice


PREVIEW_TEXT = "Às suas ordens, senhor."


def result(function, *args):
    try:
        return {"ok": function(*args)}

    except Exception as error:
        return {"error": str(error)}


def memory_items():
    return {
        subject: {"title": title, "items": list(memory.read(subject).items())}
        for subject, title in memory.SUBJECTS.items()
    }


class Panel:

    def __init__(self, jarvis, window):
        self.jarvis = jarvis
        self.window = window

    def load_panel(self):
        return {
            "preferences": settings.load(),
            "voices": settings.VOICES,
            "skills": skills.installed(),
            "memory": memory_items(),
            "google_accounts": [account for account in google_data.accounts() if account],
            "notices_connected": all(notices.connected(account) for account in dashboard.classroom_accounts())
        }

    def load_usage(self):
        # O banco pode estar fora do ar; o resto do painel continua funcionando.
        try:
            return usage.summary()

        except Exception as error:
            return {"error": str(error)}

    def save_preferences(self, values):
        def save():
            saved = settings.save(values)
            self.jarvis.apply_preferences(saved)
            return saved

        return result(save)

    def preview_voice(self, name, rate):
        def preview():
            if name not in settings.VOICES:
                raise ValueError("voz desconhecida")

            voice.play(voice.synthesize(PREVIEW_TEXT, name, rate))

        return result(preview)

    def connect_notices(self):
        # Abre o navegador para o login do mural nas contas escolhidas; só acontece quando você pede.
        return result(lambda: notices.connect(dashboard.classroom_accounts()))

    def add_skill_repo(self, url):
        def add():
            skills.add(url)
            return skills.installed()

        return result(add)

    def remove_skill_repo(self, name):
        def remove():
            skills.remove(name)
            return skills.installed()

        return result(remove)

    def forget_memory(self, subject, key):
        def forget():
            memory.forget(subject, key)
            return memory_items()

        return result(forget)

    def hide_panel(self):
        self.window.hide()

    def show(self):
        self.window.show()
        self.window.evaluate_js("refresh()")

    def closing(self):
        if self.jarvis.quitting:
            return True

        # Fechar o painel só esconde a janela.
        self.window.hide()
        return False
