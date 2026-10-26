import pytest

import drive_data


DOC = {"id": "d1", "name": "Relatório de Redes", "mimeType": drive_data.GOOGLE_DOC, "modifiedTime": "2026-10-20T10:00:00Z", "webViewLink": "https://docs.google.com/d1"}
PDF = {"id": "p1", "name": "Relatório antigo.pdf", "mimeType": "application/pdf", "modifiedTime": "2026-09-01T10:00:00Z"}
FOLDER = {"id": "f1", "name": "Relatórios", "mimeType": drive_data.FOLDER, "modifiedTime": "2026-10-25T10:00:00Z"}


class Call:

    def __init__(self, result, log=None, entry=None):
        self.result = result
        if log is not None:
            log.append(entry)

    def execute(self):
        return self.result


class FakeFiles:

    def __init__(self, files, contents, log):
        self.files, self.contents, self.log = files, contents, log

    def list(self, q, **kwargs):
        self.log.append(("list", q))
        return Call({"files": self.files})

    def export(self, fileId, mimeType):
        return Call(self.contents[fileId], self.log, ("export", fileId, mimeType))

    def export_media(self, fileId, mimeType):
        self.log.append(("export_media", fileId, mimeType))
        return self.contents[fileId]

    def get_media(self, fileId):
        self.log.append(("get_media", fileId))
        return Call(self.contents[fileId])

    def update(self, fileId, body):
        return Call({}, self.log, ("update", fileId, body))


class FakeDrive:

    def __init__(self, files, contents=None):
        self.log = []
        self._files = FakeFiles(files, contents or {}, self.log)

    def files(self):
        return self._files


class FakeDocs:

    def __init__(self, reply=None):
        self.log = []
        self.reply = reply or {}

    def documents(self):
        return self

    def batchUpdate(self, documentId, body):
        return Call(self.reply, self.log, (documentId, body["requests"][0]))


def test_search_lists_files_newest_first_with_links():
    drive = FakeDrive([PDF, DOC])

    result = drive_data.search_summary("Relatório", account_services=[("joao@gmail.com", drive, None)])

    assert result.splitlines() == [
        "Encontrei no Drive (2):",
        "- Relatório de Redes (documento, alterado em 20/10/2026) https://docs.google.com/d1",
        "- Relatório antigo.pdf (PDF, alterado em 01/09/2026)"
    ]


def test_quotes_in_the_name_cannot_break_the_query():
    drive = FakeDrive([])

    drive_data.search_summary("d'água", account_services=[(None, drive, None)])

    assert drive.log == [("list", "name contains 'd\\'água' and trashed = false")]


def test_login_failure_is_reported_when_nothing_was_found():
    with pytest.raises(RuntimeError, match="Não consegui entrar em uenp"):
        drive_data.find_one("x", [("uenp", RuntimeError("negado"), None)])


def test_reading_a_google_doc_exports_its_text_and_skips_folders():
    drive = FakeDrive([FOLDER, DOC], {"d1": "Introdução\nRedes de computadores".encode()})

    result = drive_data.read_summary("Relat", account_services=[(None, drive, None)])

    assert result == "Relatório de Redes:\nIntrodução\nRedes de computadores"
    assert ("export", "d1", "text/plain") in drive.log


def test_long_files_are_cut_for_the_chat():
    drive = FakeDrive([DOC], {"d1": b"a" * (drive_data.READ_LIMIT + 50)})

    result = drive_data.read_summary("Relat", account_services=[(None, drive, None)])

    assert result.endswith("mostrei só o começo]")
    assert len(result) < drive_data.READ_LIMIT + 100


def test_binary_files_are_offered_for_download_instead():
    drive = FakeDrive([PDF])

    assert "posso baixar" in drive_data.read_summary("antigo", account_services=[(None, drive, None)])


def test_download_exports_google_docs_as_word(monkeypatch, tmp_path):
    class FakeDownload:
        def __init__(self, buffer, media):
            self.buffer, self.media = buffer, media

        def next_chunk(self):
            self.buffer.write(self.media)
            return None, True

    monkeypatch.setenv("JARVIS_DOWNLOADS", str(tmp_path))
    monkeypatch.setattr("googleapiclient.http.MediaIoBaseDownload", FakeDownload)
    drive = FakeDrive([{**DOC, "name": "Relatório: Redes/2026"}], {"d1": b"docx"})

    result = drive_data.download("Relat", account_services=[(None, drive, None)])

    path = tmp_path / "Relatório_ Redes_2026.docx"
    assert path.read_bytes() == b"docx"
    assert result == f"Baixei Relatório: Redes/2026 em {path}"


def test_text_edits_only_on_google_docs():
    drive_data.check_edit("acrescentar", DOC)
    drive_data.check_edit("renomear", PDF)

    with pytest.raises(RuntimeError, match="só consigo mudar o texto de Documentos Google"):
        drive_data.check_edit("substituir", PDF)

    with pytest.raises(RuntimeError, match="não sei fazer"):
        drive_data.check_edit("apagar", DOC)


def test_append_goes_to_the_end_of_the_document():
    docs = FakeDocs()

    result = drive_data.edit("acrescentar", None, docs, DOC, "Conclusão: tudo certo.")

    assert docs.log == [("d1", {"insertText": {"endOfSegmentLocation": {}, "text": "\nConclusão: tudo certo."}})]
    assert result == "Pronto, senhor. Acrescentei o texto ao final de Relatório de Redes."


def test_replace_reports_how_many_changed():
    found = FakeDocs({"replies": [{"replaceAllText": {"occurrencesChanged": 2}}]})
    missing = FakeDocs({"replies": [{"replaceAllText": {}}]})

    assert drive_data.edit("substituir", None, found, DOC, "TCP", "UDP") == "Pronto, senhor. Troquei 2 ocorrência(s) em Relatório de Redes."
    assert "Nada foi alterado" in drive_data.edit("substituir", None, missing, DOC, "XYZ", "UDP")


def test_rename_any_file():
    drive = FakeDrive([])

    result = drive_data.edit("renomear", drive, None, PDF, "Relatório 2025.pdf")

    assert drive.log == [("update", "p1", {"name": "Relatório 2025.pdf"})]
    assert result == "Pronto, senhor. Relatório antigo.pdf agora se chama Relatório 2025.pdf."
