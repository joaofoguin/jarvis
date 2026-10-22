"""Memória do JARVIS: o que você ensina no chat fica em arquivos Markdown, um por assunto.

Cada item tem uma chave e um valor ("- toninho: Toninho Hajime"). Ensinar de novo a mesma
chave substitui o valor, então a memória não acumula repetições. Os arquivos ficam em
~/.jarvis/memoria (ou JARVIS_MEMORY), fora do Git, e podem ser editados à mão.
"""

import os
from pathlib import Path

from router import plain


SUBJECTS = {
    "usuario": "Sobre você",
    "contatos": "Contatos",
    "preferencias": "Preferências",
    "geral": "Geral"
}

# O que é sobre o próprio usuário vai sempre para a IA; o resto, só quando tem a ver com a pergunta.
ALWAYS_SENT = "usuario"

# Artigos e possessivos em volta de um nome ("pro toninho", "minha namorada").
NAME_FILLERS = {"meu", "minha", "o", "a", "pro", "pra", "para", "ao", "do", "da", "de"}

# Palavras comuns demais para dizer se um item tem a ver com a pergunta.
STOPWORDS = {
    "que", "meu", "minha", "meus", "minhas", "para", "pra", "pro", "com", "uma", "dos", "das", "nos", "nas",
    "por", "sobre", "isso", "esse", "essa", "ele", "ela", "voce", "sou", "sao", "tem", "ter", "mais",
    "como", "qual", "quais", "quando", "onde", "porque", "ser", "foi", "vai", "seu", "sua", "nao", "sim"
}

MAX_RELATED = 5


def folder():
    return Path(os.getenv("JARVIS_MEMORY") or Path.home() / ".jarvis" / "memoria")


def subject_of(subject):
    subject = plain(subject or "")
    return subject if subject in SUBJECTS else "geral"


def key_of(key):
    return plain(key)


def read(subject):
    """Itens de um assunto, como {chave: valor}."""

    path = folder() / f"{subject}.md"

    if not path.exists():
        return {}

    items = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line[2:].partition(":")

        if line.startswith("- ") and separator:
            items[key_of(key)] = value.strip()

    return items


def write(subject, items):
    folder().mkdir(parents=True, exist_ok=True)
    lines = [f"# {SUBJECTS[subject]}", ""] + [f"- {key}: {value}" for key, value in items.items()]
    (folder() / f"{subject}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def remember(subject, key, value):
    subject, key, value = subject_of(subject), key_of(key), " ".join(value.split())
    items = read(subject)
    replaced = key in items
    items[key] = value
    write(subject, items)

    return f"Certo, senhor. {'Atualizei' if replaced else 'Guardei'}: {key} = {value}."


def forget(subject, key):
    key = key_of(key)
    subjects = [subject_of(subject)] if subject else list(SUBJECTS)

    for name in subjects:
        items = read(name)

        if key in items:
            del items[key]
            write(name, items)
            return f"Certo, senhor. Esqueci {key}."

    return "Não encontrei isso na minha memória, senhor."


def words(text):
    return {word for word in plain(text).split() if len(word) >= 3 and word not in STOPWORDS}


def context(question):
    """Mensagem com o que a IA precisa saber da memória para esta pergunta. Vazia se não houver nada."""

    wanted = words(question)
    lines = [f"- {ALWAYS_SENT}/{key}: {value}" for key, value in read(ALWAYS_SENT).items()]

    related = [
        f"- {subject}/{key}: {value}"
        for subject in SUBJECTS if subject != ALWAYS_SENT
        for key, value in read(subject).items()
        if wanted & words(f"{key} {value}")
    ]

    lines += related[:MAX_RELATED]

    if not lines:
        return []

    return [{"role": "system", "content": "Sua memória (assunto/chave: valor):\n" + "\n".join(lines)}]


def contact_name(name):
    """Troca o jeito como o usuário chama alguém ("minha namorada") pelo contato salvo ("Amor")."""

    wanted = " ".join(word for word in plain(name).split() if word not in NAME_FILLERS)
    contacts = read("contatos")

    # Os apelidos antigos do .env (WHATSAPP_APELIDOS=namorada:Amor) continuam valendo.
    for pair in os.getenv("WHATSAPP_APELIDOS", "").split(","):
        alias, _, contact = pair.partition(":")

        if alias.strip() and contact.strip():
            contacts.setdefault(key_of(alias), contact.strip())

    return contacts.get(wanted) or name.strip()
