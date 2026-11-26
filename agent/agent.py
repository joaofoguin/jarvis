import os
import shutil
import socket
import threading
import subprocess
import requests

from dotenv import load_dotenv


load_dotenv()

# A API que o agente consulta: a Vercel por padrão, ou a VPS se JARVIS_URL estiver no .env.
JARVIS_URL = os.getenv("JARVIS_URL", "https://jarvis-one-opal-45.vercel.app").rstrip("/")

AGENT_TOKEN = os.getenv("AGENT_TOKEN")

# Pasta onde o Claude Code pode criar e alterar arquivos. Nada fora dela.
JARVIS_WORKSPACE = os.getenv("JARVIS_WORKSPACE")

CLAUDE_CODE_PREFIX = "claude_code:"
CLAUDE_CODE_TIMEOUT = 600

# Sem Bash: o Claude Code só lê e edita arquivos, não executa comandos.
CLAUDE_CODE_TOOLS = "Read,Edit,Write,Glob,Grep"

# Tarefas do Claude Code em andamento, para não repetir enquanto o comando segue pendente.
running_ids = set()

# Porta local usada só como trava: um segundo agente (o do desktop.app e o de "python -m agent.agent"
# juntos) não consegue abri-la e não roda, para nenhum comando ser executado duas vezes.
LOCK_PORT = 47613

# Comandos já executados cujo resultado ainda não chegou à API (a rede caiu na hora de avisar).
# Na próxima consulta, só o aviso é repetido; a ação não roda de novo.
unreported = {}


def auth_headers():
    return {"Authorization": f"Bearer {AGENT_TOKEN}"}


def finish_command(command_id, status, result):
    unreported[command_id] = (status, result)

    response = requests.post(
        f"{JARVIS_URL}/agent/commands/{command_id}/complete",
        json={"status": status, "result": result},
        headers=auth_headers(),
        timeout=10
    )

    response.raise_for_status()
    unreported.pop(command_id, None)

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
        # O pedido vai pela entrada padrão: no Windows o claude pode ser um .cmd, e um argumento com
        # quebra de linha é cortado pelo cmd.exe. Sem janela de terminal piscando na tela.
        completed = subprocess.run(
            [
                claude,
                "-p",
                "--allowedTools",
                CLAUDE_CODE_TOOLS,
                "--disallowedTools",
                "Bash",
                "--output-format",
                "text"
            ],
            input=f"{task}\n\nAo terminar, resuma em português, em poucas frases, o que foi feito.",
            cwd=JARVIS_WORKSPACE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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

    if command_id in unreported:
        finish_command(command_id, *unreported[command_id])
        return

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


def single_instance():
    """A trava do agente, ou None se outro agente já está rodando neste computador."""

    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        lock.bind(("127.0.0.1", LOCK_PORT))

    except OSError:
        lock.close()
        return None

    return lock


def start():
    """Prepara o agente. Retorna a trava, ou o motivo de não rodar."""

    if not AGENT_TOKEN:
        return "AGENT_TOKEN não encontrado no arquivo .env"

    lock = single_instance()
    return lock or "outro agente já está rodando neste computador"


def serve(lock, stop=None):
    """Busca e executa a fila a cada 5 segundos até `stop` (um threading.Event) ser ligado."""

    stop = stop or threading.Event()

    while not stop.is_set():
        try:
            check_commands()

        except Exception as error:
            print(f"[ERRO] {error}")

        stop.wait(5)

    lock.close()


def main():
    lock = start()

    if isinstance(lock, str):
        print(f"[ERRO] {lock}")
        return

    print("================================")
    print("       JARVIS AGENT")
    print("================================")
    print("Status: ONLINE")
    print()
    print("Aguardando comandos...")
    print()

    serve(lock)


if __name__ == "__main__":
    main()
