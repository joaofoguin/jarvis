import memory


def test_saving_the_same_key_replaces_instead_of_repeating():
    assert memory.remember("usuario", "apelido", "Foguinho") == "Certo, senhor. Guardei: apelido = Foguinho."
    assert memory.remember("usuario", "Apelido", "Foguinho") == "Certo, senhor. Atualizei: apelido = Foguinho."
    memory.remember("usuario", "nome", "João Pedro Silva da Rosa Lima")

    assert memory.read("usuario") == {"apelido": "Foguinho", "nome": "João Pedro Silva da Rosa Lima"}
    assert (memory.folder() / "usuario.md").read_text(encoding="utf-8") == (
        "# Sobre você\n\n- apelido: Foguinho\n- nome: João Pedro Silva da Rosa Lima\n"
    )


def test_unknown_subject_goes_to_general():
    memory.remember("qualquer", "time", "Corinthians")

    assert memory.read("geral") == {"time": "Corinthians"}


def test_contacts_resolve_names_and_numbers():
    memory.remember("contatos", "namorada", "Amor")
    memory.remember("contatos", "montanha", "+5518996357288")

    assert memory.contact_name("minha namorada") == "Amor"
    assert memory.contact_name("pro Montanha") == "+5518996357288"
    assert memory.contact_name("Toninho Supermercado") == "Toninho Supermercado"


def test_old_env_aliases_still_work(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APELIDOS", "mae:Mãe")

    assert memory.contact_name("minha mãe") == "Mãe"


def test_context_sends_user_subject_and_only_related_items():
    memory.remember("usuario", "apelido", "Foguinho")
    memory.remember("geral", "faculdade", "Ciência da Computação na UENP")
    memory.remember("preferencias", "time", "Corinthians")

    assert memory.context("que horas abre a biblioteca da UENP?") == [{
        "role": "system",
        "content": "Sua memória (assunto/chave: valor):\n- usuario/apelido: Foguinho\n"
                   "- geral/faculdade: Ciência da Computação na UENP"
    }]


def test_context_empty_without_memory():
    assert memory.context("qual a capital da França?") == []


def test_forget():
    memory.remember("contatos", "toninho", "Toninho Hajime")

    assert memory.forget("contatos", "Toninho") == "Certo, senhor. Esqueci toninho."
    assert memory.read("contatos") == {}
    assert memory.forget("contatos", "toninho") == "Não encontrei isso na minha memória, senhor."
