import pytest

from desktop import core
from llm import LLMError


@pytest.fixture
def actions(monkeypatch):
    executed = []
    monkeypatch.setattr(core, "run_action", executed.append)
    return executed


def test_known_command_runs_locally_without_ai(actions, monkeypatch):
    monkeypatch.setattr(core, "ask_llm", lambda *args: pytest.fail("não deveria chamar a IA"))

    assert core.reply_to("abra o bloco de notas", []) == ("Abrindo o Bloco de Notas, senhor.", None)
    assert actions == ["open_app:notepad"]


def test_ai_answer_uses_recent_history(actions, monkeypatch):
    received = {}

    def ask(text, source, history, tools):
        received["history"] = history
        return "Brasília, senhor.", None

    monkeypatch.setattr(core, "ask_llm", ask)
    history = [{"role": "user", "content": str(n)} for n in range(10)]

    assert core.reply_to("e a capital?", history) == ("Brasília, senhor.", None)
    assert received["history"] == history[-core.HISTORY_LIMIT:]
    assert actions == []


def test_ai_chosen_action_runs_locally(actions, monkeypatch):
    monkeypatch.setattr(core, "ask_llm", lambda *args: ("Abrindo, senhor.", "open_website:whatsapp"))

    core.reply_to("quero mandar mensagem para minha mãe", [])

    assert actions == ["open_website:whatsapp"]


def test_claude_code_task_is_returned_for_background(actions, monkeypatch):
    received = []
    monkeypatch.setattr(core, "call_claude_code", lambda task: received.append(task) or ("completed", "ok"))

    answer, task = core.reply_to("peça ao Claude para criar ola.py", [])

    assert actions == []
    assert task() == "Claude Code terminou: ok"
    assert received == ["criar ola.py"]


def test_ai_failure_gives_friendly_answer(actions, monkeypatch):
    def fail(*args):
        raise LLMError("sem saldo")

    monkeypatch.setattr(core, "ask_llm", fail)

    assert core.reply_to("conte uma piada", [])[0].startswith("Desculpe, senhor.")


def test_action_failure_is_reported(monkeypatch):
    def broken(command):
        raise FileNotFoundError("notepad.exe")

    monkeypatch.setattr(core, "run_action", broken)

    assert "notepad.exe" in core.reply_to("abra o bloco de notas", [])[0]


def test_run_task_reports_result(monkeypatch):
    monkeypatch.setattr(core, "call_claude_code", lambda task: ("completed", "Criei ola.py."))

    assert core.run_task("criar ola.py") == "Claude Code terminou: Criei ola.py."


def test_agenda_request_skips_ai_and_runs_in_background(actions, monkeypatch):
    monkeypatch.setattr(core, "ask_llm", lambda *args: pytest.fail("não deveria chamar a IA"))
    monkeypatch.setattr(core.google_data, "agenda_summary", lambda days, services, request: f"agenda de {days} dias")

    answer, task = core.reply_to("o que tenho amanhã?", [])

    assert task() == "agenda de 2 dias"


def test_ai_can_choose_classroom_tool(actions, monkeypatch):
    offered = {}

    def ask(text, source, history, tools):
        offered["names"] = {t["function"]["name"] for t in tools}
        return "Um momento, senhor.", "google_classroom"

    monkeypatch.setattr(core, "ask_llm", ask)
    monkeypatch.setattr(core.google_data, "classroom_summary", lambda services, request: "nada pendente")

    answer, task = core.reply_to("tenho algo para entregar na faculdade?", [])

    assert {"ver_agenda", "ver_tarefas_classroom"} <= offered["names"]
    assert task() == "nada pendente"


def test_google_errors_become_friendly_text(actions, monkeypatch):
    def broken(days, services, request):
        raise RuntimeError("Arquivo credentials.json não encontrado")

    monkeypatch.setattr(core.google_data, "agenda_summary", broken)

    answer, task = core.reply_to("minha agenda", [])

    assert task().startswith("Desculpe, senhor. Não consegui consultar o Google: Arquivo credentials.json")


def test_youtube_request_runs_in_background(actions, monkeypatch):
    monkeypatch.setattr(core, "ask_llm", lambda *args: pytest.fail("não deveria chamar a IA"))
    monkeypatch.setattr(core.google_data, "youtube_summary", lambda request: f"métricas para: {request}")

    answer, task = core.reply_to("como estão os insights do meu vídeo", [])

    assert task() == "métricas para: como estão os insights do meu vídeo"


def test_youtube_report_saved_as_pdf_when_asked(actions, monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(core.reports, "open_file", lambda path: None)
    monkeypatch.setattr(core.google_data, "youtube_summary", lambda request: "Canal Na Base do Bit: 100 inscritos 🎬")

    answer, task = core.reply_to("veja os insights do youtube e gere um relatório em pdf", [])
    result = task()

    pdfs = list(tmp_path.glob("relatorio_youtube_*.pdf"))
    assert len(pdfs) == 1
    assert pdfs[0].read_bytes().startswith(b"%PDF")
    assert f"Relatório salvo em {pdfs[0]}" in result


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr(core, "pending_action", None)
    monkeypatch.setattr(core.whatsapp_app, "send", lambda phone, text: messages.append((phone, text)) or "enviada")
    monkeypatch.setattr(core.icloud_data, "address_cards", lambda: [
        "BEGIN:VCARD\r\nFN:Amor❤️🥵\r\nTEL:+5514996872005\r\nEND:VCARD",
        "BEGIN:VCARD\r\nFN:Julya Namorada Jow\r\nTEL:(14) 99635-4039\r\nEND:VCARD",
    ])
    core.memory.remember("contatos", "namorada", "Amor")
    return messages


def test_whatsapp_message_waits_for_confirmation(actions, sent):
    answer, task = core.reply_to("mande mensagem para minha namorada no whatsapp dizendo Oi amor, já estou em casa", [])

    assert answer == (
        'Enviar "Oi amor, já estou em casa" para Amor❤️🥵 (+5514996872005) no WhatsApp? Responda "sim" para confirmar.'
    )
    assert task is None and sent == []

    answer, task = core.reply_to("Sim", [])

    assert task() == "enviada"
    assert sent == [("5514996872005", "Oi amor, já estou em casa")]


def test_whatsapp_unknown_contact_is_not_queued(actions, sent):
    answer, task = core.reply_to("manda pro Zé no zap: oi", [])

    assert answer == "Desculpe, senhor. Não consegui achar o número: não encontrei Zé com telefone nos seus contatos do iCloud"
    assert core.pending_action is None


def test_whatsapp_message_cancelled(actions, sent):
    core.reply_to("manda pro Amor no zap: oi", [])

    assert core.reply_to("não", []) == ("Certo, senhor. Cancelado.", None)
    assert sent == []


def test_ai_chosen_whatsapp_also_asks_first(actions, sent, monkeypatch):
    monkeypatch.setattr(core, "ask_llm", lambda *args: ("Certo.", 'whatsapp_enviar:["Amor", "oi"]'))

    answer, task = core.reply_to("avisa a Amor que cheguei", [])

    assert task is None and "Responda \"sim\"" in answer and sent == []


def test_instagram_runs_in_background(actions, monkeypatch):
    monkeypatch.setattr(core.browser, "instagram_unread", lambda: "Nenhuma mensagem nova no Instagram, senhor.")

    answer, task = core.reply_to("verifique se há novas mensagens no instagram", [])

    assert task() == "Nenhuma mensagem nova no Instagram, senhor."


def test_contact_lookup_uses_aliases(actions, monkeypatch):
    monkeypatch.setenv("WHATSAPP_APELIDOS", "namorada:Amor")
    monkeypatch.setattr(core.icloud_data, "contact_summary", lambda name: f"procurei {name}")

    answer, task = core.reply_to("qual o número da minha namorada?", [])

    assert task() == "procurei Amor"


def test_agenda_adds_icloud_when_configured(actions, monkeypatch):
    monkeypatch.setattr(core.google_data, "agenda_summary", lambda *args: "Google")
    monkeypatch.setattr(core.icloud_data, "agenda_summary", lambda days: f"iCloud {days}")
    monkeypatch.setattr(core.icloud_data, "configured", lambda: True)

    assert core.reply_to("o que tenho hoje?", [])[1]() == "Google\n\niCloud 1"

    monkeypatch.setattr(core.icloud_data, "configured", lambda: False)

    assert core.reply_to("o que tenho hoje?", [])[1]() == "Google"


def test_contact_lookup_uses_memory(actions, monkeypatch):
    monkeypatch.setattr(core.icloud_data, "contact_summary", lambda name: f"procurei {name}")
    core.memory.remember("contatos", "namorada", "Amor")

    assert core.reply_to("qual o número da minha namorada?", [])[1]() == "procurei Amor"


def test_related_memory_goes_to_the_ai(actions, monkeypatch):
    received = {}

    def ask(text, source, history, tools):
        received["history"] = history
        return "Ok.", None

    monkeypatch.setattr(core, "ask_llm", ask)
    core.memory.remember("geral", "faculdade", "UENP")

    core.reply_to("a UENP tem aula amanhã?", [])

    assert received["history"][0]["content"] == "Sua memória (assunto/chave: valor):\n- geral/faculdade: UENP"


def llm_replies(monkeypatch, *replies):
    calls = []

    def ask(text, source, history, tools):
        calls.append({"history": history, "tools": [tool["function"]["name"] for tool in tools]})
        return replies[len(calls) - 1]

    monkeypatch.setattr(core, "ask_llm", ask)
    return calls


def test_conversation_continues_after_ai_saves_memory(actions, sent, monkeypatch):
    calls = llm_replies(
        monkeypatch,
        ("", 'memoria_lembrar:["contatos", "toninho", "Amor"]'),
        ("", 'whatsapp_enviar:["toninho", "Saudações do JARVIS, em nome do Foguinho."]')
    )

    answer, task = core.reply_to("toninho é a Amor, manda saudações suas pra ele", [])

    assert answer == (
        "Certo, senhor. Guardei: toninho = Amor. "
        'Enviar "Saudações do JARVIS, em nome do Foguinho." para Amor❤️🥵 (+5514996872005) no WhatsApp? '
        'Responda "sim" para confirmar.'
    )
    assert 'memoria_lembrar:["contatos", "toninho", "Amor"]: Certo, senhor.' in calls[1]["history"][-1]["content"]


def test_only_memory_request_gets_short_answer(actions, monkeypatch):
    llm_replies(monkeypatch, ("", 'memoria_lembrar:["usuario", "apelido", "Foguinho"]'), ("OK.", None))

    assert core.reply_to("aprenda, me chame de Foguinho", []) == ("Certo, senhor. Guardei: apelido = Foguinho.", None)


def test_contact_saved_as_number(actions, sent, monkeypatch):
    core.memory.remember("contatos", "montanha", "+5518996357288")
    llm_replies(monkeypatch, ("", 'whatsapp_enviar:["Montanha", "oi"]'))

    assert core.reply_to("avisa o Montanha", [])[0] == (
        'Enviar "oi" para Montanha (+5518996357288) no WhatsApp? Responda "sim" para confirmar.'
    )


@pytest.fixture
def drive(monkeypatch):
    from tests.test_drive_data import DOC, FakeDocs, FakeDrive

    docs = FakeDocs()
    monkeypatch.setattr(core, "pending_action", None)
    monkeypatch.setattr(core.drive_data, "services", lambda request: [(None, FakeDrive([DOC]), docs)])
    return docs


def test_drive_edit_waits_for_confirmation(actions, drive, monkeypatch):
    monkeypatch.setattr(core, "ask_llm", lambda *args: ("Certo.", 'google_drive:["acrescentar", "Redes", "Fim.", ""]'))

    answer, task = core.reply_to("acrescente Fim. no relatório de redes", [])

    assert answer == 'Acrescentar ao final de "Relatório de Redes" o texto: "Fim."? Responda "sim" para confirmar.'
    assert task is None and drive.log == []

    answer, task = core.reply_to("sim", [])

    assert task() == "Pronto, senhor. Acrescentei o texto ao final de Relatório de Redes."
    assert drive.log == [("d1", {"insertText": {"endOfSegmentLocation": {}, "text": "\nFim."}})]


def test_drive_edit_cancelled(actions, drive, monkeypatch):
    monkeypatch.setattr(core, "ask_llm", lambda *args: ("Certo.", 'google_drive:["renomear", "Redes", "Novo", ""]'))

    core.reply_to("renomeie o relatório de redes para Novo", [])

    assert core.reply_to("não", []) == ("Certo, senhor. Cancelado.", None)
    assert drive.log == []


def test_drive_search_runs_in_background_without_ai(actions, monkeypatch):
    monkeypatch.setattr(core, "ask_llm", lambda *args: pytest.fail("não deveria chamar a IA"))
    monkeypatch.setattr(core.drive_data, "search_summary", lambda name, request: f"procurei {name}")

    answer, task = core.reply_to("procure o relatório de Redes no Drive", [])

    assert task() == "procurei relatório de Redes"


def test_ai_sees_result_and_takes_next_step(actions, monkeypatch):
    monkeypatch.setattr(core.google_data, "agenda_summary", lambda *args: "Prova às 10h")
    monkeypatch.setattr(core.icloud_data, "configured", lambda: False)
    calls = llm_replies(
        monkeypatch,
        ("Um momento, senhor.", "google_agenda:1"),
        ("Abrindo o Bloco de Notas, senhor.", "open_app:notepad"),
        ("Anotei a prova, senhor.", None)
    )
    recorded = []

    answer, task = core.reply_to("prepare minha manhã", [], recorded.append)

    assert answer == "Um momento, senhor." and actions == []
    assert task() == "Prova às 10h\n\nAbrindo o Bloco de Notas, senhor.\n\nAnotei a prova, senhor."
    assert actions == ["open_app:notepad"]
    assert "google_agenda:1: Prova às 10h" in calls[1]["history"][-1]["content"]
    assert recorded == [core.executed("google_agenda:1"), core.executed("open_app:notepad")]


def test_steps_stop_at_the_limit(actions, monkeypatch):
    commands = ["open_app:notepad", "open_app:calc", "open_website:youtube", "open_website:whatsapp", "open_app:paint"]
    llm_replies(monkeypatch, *[("", command) for command in commands])

    core.reply_to("prepare meu dia", [])

    assert actions == commands[:core.MAX_STEPS]


def test_repeated_action_ends_the_request(actions, monkeypatch):
    llm_replies(monkeypatch, *[("Abrindo o Bloco de Notas, senhor.", "open_app:notepad")] * 2)

    assert core.reply_to("quero anotar uma coisa", []) == ("Abrindo o Bloco de Notas, senhor.", None)
    assert actions == ["open_app:notepad"]


def test_ai_failure_after_an_action_keeps_the_result(actions, monkeypatch):
    replies = iter([("Abrindo o Bloco de Notas, senhor.", "open_app:notepad")])

    def ask(*args):
        try:
            return next(replies)
        except StopIteration:
            raise LLMError("sem saldo")

    monkeypatch.setattr(core, "ask_llm", ask)

    assert core.reply_to("quero anotar uma coisa", []) == ("Abrindo o Bloco de Notas, senhor.", None)


def test_router_command_is_recorded_for_retry(actions, monkeypatch):
    recorded = []

    core.reply_to("abra o bloco de notas", [], recorded.append)

    assert recorded == [core.executed("open_app:notepad")]


def test_confirmed_message_is_recorded_when_sent(actions, sent, monkeypatch):
    recorded = []
    core.reply_to("manda pro Amor no zap: oi", [], recorded.append)

    assert recorded == []

    core.reply_to("sim", [], recorded.append)[1]()

    assert recorded == [core.executed('whatsapp_enviar:["Amor", "oi"]')]


def test_failed_claude_code_is_not_retried_with_another_task(actions, monkeypatch):
    runs = []
    monkeypatch.setattr(core, "call_claude_code", lambda task: runs.append(task) or ("failed", "sem login"))
    llm_replies(
        monkeypatch,
        ("Pedi ao Claude Code.", "claude_code:crie uma calculadora"),
        ("Vou tentar de novo.", "claude_code:crie uma calculadora simples em Python")
    )

    answer, task = core.reply_to("crie uma calculadora", [])

    assert task() == "O Claude Code falhou: sem login"
    assert runs == ["crie uma calculadora"]
