import os
import sys
import types

import pytest

import local_files
from desktop import core
from router import command_for_tool


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    folder = tmp_path / "trabalho"
    (folder / "site").mkdir(parents=True)
    (folder / "site" / "index.html").write_text("<h1>oi</h1>")
    (folder / "virus.bat").write_text("echo")
    monkeypatch.setenv("JARVIS_WORKSPACE", str(folder))
    opened, trashed = [], []
    monkeypatch.setattr(local_files.os, "startfile", opened.append, raising=False)
    monkeypatch.setitem(sys.modules, "send2trash", types.SimpleNamespace(send2trash=trashed.append))
    return folder, opened, trashed


def test_open_finds_the_file_inside_the_workspace(workspace):
    folder, opened, _ = workspace
    command, _ = command_for_tool("abrir_arquivo", {"arquivo": "index.html"})

    answer, task = core.run_command(command, "", "abra o site")

    assert opened == [folder / "site" / "index.html"]
    assert answer == f"Abri {os.path.join('site', 'index.html')}, senhor."


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


def test_files_outside_the_workspace_are_not_found(workspace, tmp_path):
    (tmp_path / "segredo.txt").write_text("x")

    with pytest.raises(RuntimeError, match="não achei"):
        local_files.find("segredo.txt")


def test_without_workspace_nothing_happens(monkeypatch):
    monkeypatch.delenv("JARVIS_WORKSPACE", raising=False)
    command, _ = command_for_tool("abrir_arquivo", {"arquivo": "index.html"})

    answer, _ = core.run_command(command, "", "abra")

    assert "JARVIS_WORKSPACE" in answer


def test_invalid_tool_arguments_are_refused():
    assert command_for_tool("apagar_arquivo", {"arquivo": ""}) is None
