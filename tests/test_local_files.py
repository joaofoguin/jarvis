import os
import sys
import types

import pytest

import local_files
from desktop import core
from router import command_for_tool


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    home = tmp_path / "home"
    folder = home / "Downloads"
    (folder / "site").mkdir(parents=True)
    (folder / "site" / "index.html").write_text("<h1>oi</h1>")
    (folder / "virus.bat").write_text("echo")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    opened, trashed = [], []
    monkeypatch.setattr(local_files.os, "startfile", opened.append, raising=False)
    monkeypatch.setitem(sys.modules, "send2trash", types.SimpleNamespace(send2trash=trashed.append))
    return folder, opened, trashed


def test_open_finds_the_file_inside_the_workspace(workspace):
    folder, opened, _ = workspace
    command, _ = command_for_tool("abrir_arquivo", {"arquivo": "index.html"})

    answer, task = core.run_command(command, "", "abra o site")

    assert opened == [folder / "site" / "index.html"]
    assert answer == f"Abri {os.path.join('Downloads', 'site', 'index.html')}, senhor."


def test_programs_and_scripts_are_never_opened(workspace):
    _, opened, _ = workspace

    answer = local_files.open_file(local_files.find("virus.bat"))

    assert opened == []
    assert "programa ou script" in answer


def test_delete_asks_first_and_goes_to_the_trash(workspace):
    folder, _, trashed = workspace
    command, _ = command_for_tool("apagar_arquivo", {"arquivo": "index"})

    answer, task = core.run_command(command, "", "apague o index")

    assert "Responda \"sim\"" in answer and trashed == []
    reply, task = core.reply_to("sim", [])
    assert "Lixeira" in task()
    assert trashed == [str(folder / "site" / "index.html")]


def test_documents_and_the_workspace_are_searched_too(workspace, monkeypatch, tmp_path):
    folder, opened, _ = workspace
    (folder.parent / "Documents").mkdir()
    (folder.parent / "Documents" / "trabalho.docx").write_text("x")
    (tmp_path / "projetos").mkdir()
    (tmp_path / "projetos" / "app.html").write_text("x")
    monkeypatch.setenv("JARVIS_WORKSPACE", str(tmp_path / "projetos"))

    assert local_files.find("trabalho").name == "trabalho.docx"
    assert local_files.find("app.html").name == "app.html"


@pytest.mark.parametrize("hidden", [".ssh/id_rsa.txt", "AppData/Roaming/x.txt", "site/.env", "site/google_token_a.json"])
def test_hidden_system_and_secret_files_are_off_limits(workspace, hidden):
    folder, _, _ = workspace
    path = folder.parent / hidden if hidden.startswith((".ssh", "AppData")) else folder / hidden
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")

    with pytest.raises(RuntimeError, match="não achei"):
        local_files.find(path.name)


def test_files_outside_the_user_folders_are_not_found(workspace, tmp_path):
    (tmp_path / "segredo.txt").write_text("x")

    with pytest.raises(RuntimeError, match="não achei"):
        local_files.find("segredo.txt")


def test_invalid_tool_arguments_are_refused():
    assert command_for_tool("apagar_arquivo", {"arquivo": ""}) is None
