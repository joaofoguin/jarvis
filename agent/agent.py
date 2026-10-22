import os
import shutil
import time
import threading
import subprocess
import requests

from dotenv import load_dotenv


load_dotenv()

JARVIS_URL = "https://jarvis-one-opal-45.vercel.app"

AGENT_TOKEN = os.getenv("AGENT_TOKEN")

# Pasta onde o Claude Code pode criar e alterar arquivos. Nada fora dela.
JARVIS_WORKSPACE = os.getenv("JARVIS_WORKSPACE")

CLAUDE_CODE_PREFIX = "claude_code:"
CLAUDE_CODE_TIMEOUT = 600

# Sem Bash: o Claude Code só lê e edita arquivos, não executa comandos.
CLAUDE_CODE_TOOLS = "Read,Edit,Write,Glob,Grep"

# Tarefas do Claude Code em andamento, para não repetir enquanto o comando segue pendente.
running_ids = set()


def auth_headers():
    return {"Authorization": f"Bearer {AGENT_TOKEN}"}


def finish_command(command_id, status, result):
    response = requests.post(
        f"{JARVIS_URL}/agent/commands/{command_id}/complete",
        json={"status": status, "result": result},
        headers=auth_headers(),
        timeout=10
    )

    response.raise_for_status()

    if response.json().get("success"):
        print(f"[COMANDO {status.upper()}] ID={command_id} | {result}")


def run_action(command_text):
    """Executa uma ação permitida. Retorna a descrição do resultado ou None se não for permitida."""

    if command_text == "open_app:notepad":
        print("[AÇÃO] Abrindo Bloco de Notas...")

        subprocess.Popen(["notepad.exe"])

        return "Bloco de Notas aberto"

    if command_text == "open_website:whatsapp":
        print("[AÇÃO] Abrindo WhatsApp Web...")

        subprocess.Popen([
            "cmd",
            "/c",
            "start",
            "",
            "https://web.whatsapp.com"
        ])

        return "WhatsApp Web aberto no navegador"

    return None


def run_claude_code(command_id, task):
    """Roda o Claude Code em segundo plano e informa o resultado quando terminar."""

    try:
        status, result = call_claude_code(task)
        finish_command(command_id, status, result)

    except Exception as error:
        print(f"[ERRO] {error}")

    finally:
        running_ids.discard(command_id)


def call_claude_code(task):

    if not JARVIS_WORKSPACE or not os.path.isdir(JARVIS_WORKSPACE):
        return "failed", "JARVIS_WORKSPACE não configurado ou a pasta não existe"

    claude = shutil.which("claude")

    if not claude:
        return "failed", "Claude Code não encontrado. Instale e faça login com o comando claude"

    print(f"[AÇÃO] Claude Code: {task}")

    try:
        completed = subprocess.run(
            [
                claude,
                "-p",
                f"{task}\n\nAo terminar, resuma em português, em poucas frases, o que foi feito.",
                "--allowedTools",
                CLAUDE_CODE_TOOLS,
                "--disallowedTools",
                "Bash",
                "--output-format",
                "text"
            ],
            cwd=JARVIS_WORKSPACE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=CLAUDE_CODE_TIMEOUT
        )

    except subprocess.TimeoutExpired:
        return "failed", f"Claude Code passou de {CLAUDE_CODE_TIMEOUT} segundos"

    if completed.returncode != 0:
        return "failed", (completed.stderr or completed.stdout).strip()[-500:]

    return "completed", completed.stdout.strip()[-500:]


def execute_command(command_id, command_text):

    if command_text.startswith(CLAUDE_CODE_PREFIX):

        if command_id not in running_ids:
            running_ids.add(command_id)

            threading.Thread(
                target=run_claude_code,
                args=(command_id, command_text[len(CLAUDE_CODE_PREFIX):]),
                daemon=True
            ).start()

        return

    try:
        result = run_action(command_text)

    except Exception as error:
        print(f"[ERRO NA AÇÃO] {error}")
        finish_command(command_id, "failed", repr(error))
        return

    if result is None:
        print(f"[AVISO] Comando não autorizado: {command_text}")
        finish_command(command_id, "rejected", "Comando não está na lista permitida")
        return

    finish_command(command_id, "completed", result)


def check_commands():

    response = requests.get(
        f"{JARVIS_URL}/agent/commands",
        headers=auth_headers(),
        timeout=10
    )

    response.raise_for_status()

    commands = response.json()

    for command in commands:

        command_id = command["id"]
        command_text = command["command"]

        print(
            f"[COMANDO RECEBIDO] "
            f"ID={command_id} | "
            f"Comando={command_text}"
        )

        execute_command(command_id, command_text)


def main():

    if not AGENT_TOKEN:
        print("[ERRO] AGENT_TOKEN não encontrado no arquivo .env")
        return

    print("================================")
    print("       JARVIS AGENT")
    print("================================")
    print("Status: ONLINE")
    print()
    print("Aguardando comandos...")
    print()

    while True:

        try:
            check_commands()

        except Exception as error:
            print(f"[ERRO] {error}")

        time.sleep(5)


if __name__ == "__main__":
    main()
