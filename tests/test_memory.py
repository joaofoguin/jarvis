import memory


def test_alias_is_learned_and_used_for_contacts():
    assert memory.remember("minha namorada é a Amor") == "Certo, senhor. Vou lembrar que namorada é Amor."

    assert memory.contact_name("minha namorada") == "Amor"
    assert memory.contact_name("namorada") == "Amor"
    assert memory.contact_name("Pedro") == "Pedro"
    assert (memory.folder() / "apelidos.md").read_text(encoding="utf-8") == "# Apelidos\n\n- namorada: Amor\n"


def test_alias_is_replaced_not_duplicated():
    memory.remember("minha namorada é a Amor")
    memory.remember("minha namorada se chama Julia")

    assert memory.read("apelidos") == ["namorada: Julia"]


def test_old_env_aliases_still_work(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APELIDOS", "mae:Mãe")

    assert memory.contact_name("minha mãe") == "Mãe"


def test_facts_are_saved_once():
    memory.remember("eu estudo Ciência da Computação na UENP.")
    memory.remember("eu estudo Ciência da Computação na UENP")

    assert memory.read("fatos") == ["eu estudo Ciência da Computação na UENP"]


def test_context_has_only_related_facts():
    memory.remember("eu estudo Ciência da Computação na UENP")
    memory.remember("eu torço para o Corinthians")
    memory.remember("minha namorada é a Amor")

    assert memory.context("que horas abre a biblioteca da UENP?") == [
        {"role": "system", "content": "O usuário já te ensinou:\n- eu estudo Ciência da Computação na UENP"}
    ]
    assert memory.context("qual a capital da França?") == []


def test_forget_removes_matching_items():
    memory.remember("minha namorada é a Amor")
    memory.remember("eu torço para o Corinthians")

    assert memory.forget("minha namorada é a Amor") == "Certo, senhor. Esqueci."
    assert memory.read("apelidos") == []
    assert memory.read("fatos") == ["eu torço para o Corinthians"]
    assert memory.forget("a cor do meu carro") == "Não encontrei isso na minha memória, senhor."
