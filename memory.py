"""Memória do JARVIS: o que você ensina no chat fica em arquivos Markdown, um por assunto.

Os arquivos ficam em ~/.jarvis/memoria (ou JARVIS_MEMORY), fora do Git, e podem ser
abertos e editados à mão. Para cada pergunta, só os fatos ligados a ela vão para a IA.
"""

import os
import re
from pathlib import Path

from router import plain


SUBJECTS = {"apelidos": "Apelidos", "fatos": "Fatos"}

# "minha namorada é a Amor" e "toninho está salvo como Toninho Hajime" viram apelidos.
ALIAS_PATTERNS = [
    re.compile(
        r"^(o |a )?(meu|minha) (?P<apelido>[\w ]+?) (é|e|se chama|chama-se) (o |a )?(?P<nome>.+?)[.!]?$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(o |a )?(?P<apelido>[\w ]+?) (está|esta|tá|ta|fica) salv[oa] como (o |a )?(?P<nome>.+?)[.!]?$",
        re.IGNORECASE
    )
]

# Palavras que ficam em volta de um apelido ("pro toninho", "minha namorada").
ALIAS_FILLERS = {"meu", "minha", "o", "a", "pro", "pra", "para", "ao", "do", "da", "de"}

# Fatos sobre o próprio usuário vão sempre para a IA, como o nome e o apelido dele.
PROFILE_PATTERN = re.compile(r"\b(eu sou|meu nome|me chamo|me chame|meu apelido)\b")

# Palavras comuns demais para dizer se um fato tem a ver com a pergunta.
STOPWORDS = {
    "que", "meu", "minha", "meus", "minhas", "para", "pra", "pro", "com", "uma", "dos", "das", "nos", "nas",
    "por", "sobre", "isso", "esse", "essa", "ele", "ela", "voce", "sou", "sao", "tem", "ter", "mais",
    "como", "qual", "quais", "quando", "onde", "porque", "ser", "foi", "vai", "seu", "sua", "nao", "sim"
}

MAX_FACTS = 5


def folder():
    return Path(os.getenv("JARVIS_MEMORY") or Path.home() / ".jarvis" / "memoria")


def read(subject):
    path = folder() / f"{subject}.md"

    if not path.exists():
        return []

    return [line[2:].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("- ")]


def write(subject, items):
    folder().mkdir(parents=True, exist_ok=True)
    lines = [f"# {SUBJECTS[subject]}", ""] + [f"- {item}" for item in items]
    (folder() / f"{subject}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def words(text):
    return {word for word in plain(text).split() if len(word) >= 3 and word not in STOPWORDS}


def remember(fact):
    for pattern in ALIAS_PATTERNS:
        alias = pattern.match(fact)

        if alias:
            return remember_alias(alias["apelido"], alias["nome"])

    fact = fact.strip().rstrip(".")
    items = read("fatos")

    if fact not in items:
        write("fatos", items + [fact])

    return "Certo, senhor. Vou lembrar disso."


def remember_alias(alias, contact):
    key = plain(alias)
    items = [item for item in read("apelidos") if plain(item.partition(":")[0]) != key]
    write("apelidos", items + [f"{key}: {contact.strip()}"])

    return f"Certo, senhor. Vou lembrar que {alias.strip()} é {contact.strip()}."


def forget(text):
    """Apaga os itens que têm todas as palavras importantes do pedido."""

    wanted = words(text)
    removed = 0

    for subject in SUBJECTS:
        items = read(subject)
        keep = [item for item in items if not wanted or not wanted <= words(item)]

        if len(keep) < len(items):
            removed += len(items) - len(keep)
            write(subject, keep)

    if not removed:
        return "Não encontrei isso na minha memória, senhor."

    return "Certo, senhor. Esqueci." if removed == 1 else f"Certo, senhor. Esqueci {removed} itens."


def context(question):
    """Mensagem com os fatos ligados à pergunta, para ir junto à IA. Vazia se nada tiver a ver."""

    wanted = words(question)
    items = [item for subject in SUBJECTS for item in read(subject)]
    profile = [item for item in items if PROFILE_PATTERN.search(plain(item))]
    related = (profile + [item for item in items if item not in profile and wanted & words(item)])[:MAX_FACTS]

    if not related:
        return []

    return [{"role": "system", "content": "O usuário já te ensinou:\n" + "\n".join(f"- {item}" for item in related)}]


def contact_name(name):
    """Troca um apelido ("minha namorada") pelo nome do contato ("Amor").

    O pedido precisa ser só o apelido: "toninho" vira "Toninho Hajime", mas "Toninho Supermercado" não.
    """

    text = " ".join(word for word in plain(name).split() if word not in ALIAS_FILLERS)

    # Os apelidos antigos do .env (WHATSAPP_APELIDOS=namorada:Amor) continuam valendo.
    for item in read("apelidos") + os.getenv("WHATSAPP_APELIDOS", "").split(","):
        alias, _, contact = item.partition(":")

        if alias.strip() and contact.strip() and plain(alias) == text:
            return contact.strip()

    return name.strip()
