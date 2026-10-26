"""Google Drive para a janela de chat: buscar, ler, baixar e editar arquivos quando o usuário pede.

O Drive pede permissões de escrita, então tem um login próprio ("drive"), separado do login só de leitura
da Agenda e do Classroom. Toda edição passa antes pela confirmação do usuário (desktop/core.py).
"""

import io
import os
import re
from pathlib import Path

from google_data import accounts, get_credentials, login_error, short_error


SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents"
]

KIND = "drive"

MAX_FILES = 10

# Um arquivo lido vai inteiro para o chat e para o histórico da IA; acima disso, só o começo.
READ_LIMIT = 4000

FOLDER = "application/vnd.google-apps.folder"
GOOGLE_DOC = "application/vnd.google-apps.document"

# Arquivos do Google não têm conteúdo próprio: são exportados num formato comum.
EXPORT_DOWNLOAD = {
    GOOGLE_DOC: ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf")
}
EXPORT_TEXT = {
    GOOGLE_DOC: "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain"
}
TEXT_TYPES = ("text/", "application/json", "application/xml", "application/csv")

KINDS = {
    GOOGLE_DOC: "documento",
    "application/vnd.google-apps.spreadsheet": "planilha",
    "application/vnd.google-apps.presentation": "apresentação",
    FOLDER: "pasta",
    "application/pdf": "PDF"
}


def downloads_folder():
    return Path(os.getenv("JARVIS_DOWNLOADS") or Path.home() / "Downloads" / "JARVIS")


def services(request=""):
    """[(conta, drive, docs)] para cada conta. Se o login falhar, drive é o erro e docs é None."""

    from googleapiclient.discovery import build

    result = []

    for account in accounts(request):
        try:
            creds = get_credentials(account, SCOPES, KIND)
            result.append((
                account,
                build("drive", "v3", credentials=creds, cache_discovery=False),
                build("docs", "v1", credentials=creds, cache_discovery=False)
            ))

        except Exception as error:
            result.append((account, error, None))

    return result


def query_for(name):
    # Aspas e barras invertidas precisam de escape dentro da consulta do Drive.
    escaped = name.replace("\\", "\\\\").replace("'", "\\'")
    return f"name contains '{escaped}' and trashed = false"


def find(name, account_services):
    """[(conta, drive, docs, arquivo)] cujo nome contém `name`, dos mais recentes para os mais antigos."""

    found = []
    errors = []

    for account, drive, docs in account_services:
        if isinstance(drive, Exception):
            errors.append(login_error(account, drive))
            continue

        files = drive.files().list(
            q=query_for(name), orderBy="modifiedTime desc", pageSize=MAX_FILES,
            fields="files(id, name, mimeType, modifiedTime, webViewLink)"
        ).execute().get("files", [])
        found += [(account, drive, docs, file) for file in files]

    if not found and errors:
        raise RuntimeError("; ".join(errors))

    return sorted(found, key=lambda item: item[3].get("modifiedTime", ""), reverse=True)


def find_one(name, account_services):
    """O arquivo mais recente com esse nome, ou um erro que o chat consegue mostrar."""

    found = [item for item in find(name, account_services) if item[3]["mimeType"] != FOLDER]

    if not found:
        raise RuntimeError(f"não achei nenhum arquivo com \"{name}\" no nome no seu Drive")

    return found[0]


def describe(account, file, many):
    kind = KINDS.get(file["mimeType"], "arquivo")
    when = file.get("modifiedTime", "")[:10]
    date = f", alterado em {when[8:10]}/{when[5:7]}/{when[:4]}" if when else ""
    where = f" ({account})" if many and account else ""
    return f"{file['name']} ({kind}{date}){where}"


def search_summary(name, request="", account_services=None):
    account_services = account_services or services(request)
    found = find(name, account_services)[:MAX_FILES]

    if not found:
        return f"Não achei nada com \"{name}\" no nome no seu Drive, senhor."

    many = len(account_services) > 1
    lines = [f"Encontrei no Drive ({len(found)}):"]
    lines += [f"- {describe(account, file, many)} {file.get('webViewLink', '')}".rstrip() for account, _, _, file in found]
    return "\n".join(lines)


def read_summary(name, request="", account_services=None):
    """O texto do arquivo, para o usuário ver e a IA poder resumir ou responder sobre ele depois."""

    account, drive, _, file = find_one(name, account_services or services(request))
    kind = file["mimeType"]

    if kind in EXPORT_TEXT:
        content = drive.files().export(fileId=file["id"], mimeType=EXPORT_TEXT[kind]).execute()
    elif kind.startswith(TEXT_TYPES):
        content = drive.files().get_media(fileId=file["id"]).execute()
    else:
        return f"Não consigo ler {file['name']} aqui no chat, senhor, mas posso baixar o arquivo."

    text = (content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content).strip()

    if len(text) > READ_LIMIT:
        text = text[:READ_LIMIT] + "\n[…o arquivo continua; mostrei só o começo]"

    return f"{file['name']}:\n{text or '(arquivo vazio)'}"


def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .") or "arquivo"


def download(name, request="", account_services=None):
    from googleapiclient.http import MediaIoBaseDownload

    account, drive, _, file = find_one(name, account_services or services(request))
    kind = file["mimeType"]
    filename = safe_name(file["name"])

    if kind in EXPORT_DOWNLOAD:
        export_type, extension = EXPORT_DOWNLOAD[kind]
        media = drive.files().export_media(fileId=file["id"], mimeType=export_type)
        filename += "" if filename.lower().endswith(extension) else extension
    elif kind.startswith("application/vnd.google-apps."):
        return f"Esse tipo de arquivo do Google ({file['name']}) não pode ser baixado, senhor."
    else:
        media = drive.files().get_media(fileId=file["id"])

    folder = downloads_folder()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, media)
    done = False

    while not done:
        _, done = downloader.next_chunk()

    # Grava só no fim, para um download que falhou não deixar um arquivo pela metade.
    path.write_bytes(buffer.getvalue())
    return f"Baixei {file['name']} em {path}"


# Edições permitidas: a IA escolhe uma delas, nunca um comando livre.
EDITS = {"acrescentar", "substituir", "renomear"}


def edit_question(action, file, text, new_text):
    """A pergunta de confirmação mostrada antes de editar."""

    if action == "acrescentar":
        return f"Acrescentar ao final de \"{file['name']}\" o texto: \"{text}\"?"

    if action == "substituir":
        return f"Trocar \"{text}\" por \"{new_text}\" em \"{file['name']}\"?"

    return f"Renomear \"{file['name']}\" para \"{text}\"?"


def check_edit(action, file):
    if action not in EDITS:
        raise RuntimeError(f"não sei fazer a edição \"{action}\"")

    # O texto só é editado em Documentos Google, onde a formatação é preservada.
    if action != "renomear" and file["mimeType"] != GOOGLE_DOC:
        raise RuntimeError(f"só consigo mudar o texto de Documentos Google; {file['name']} é outro tipo de arquivo")


def edit(action, drive, docs, file, text, new_text=""):
    """Aplica uma edição já confirmada e devolve o texto para o chat."""

    check_edit(action, file)

    try:
        if action == "renomear":
            drive.files().update(fileId=file["id"], body={"name": text}).execute()
            return f"Pronto, senhor. {file['name']} agora se chama {text}."

        if action == "acrescentar":
            docs.documents().batchUpdate(documentId=file["id"], body={"requests": [
                {"insertText": {"endOfSegmentLocation": {}, "text": "\n" + text}}
            ]}).execute()
            return f"Pronto, senhor. Acrescentei o texto ao final de {file['name']}."

        result = docs.documents().batchUpdate(documentId=file["id"], body={"requests": [
            {"replaceAllText": {"containsText": {"text": text, "matchCase": False}, "replaceText": new_text}}
        ]}).execute()

    except Exception as error:
        return f"Desculpe, senhor. Não consegui editar {file['name']}: {short_error(error)}"

    changed = result.get("replies", [{}])[0].get("replaceAllText", {}).get("occurrencesChanged", 0)

    if not changed:
        return f"Não encontrei \"{text}\" em {file['name']}, senhor. Nada foi alterado."

    return f"Pronto, senhor. Troquei {changed} ocorrência(s) em {file['name']}."
