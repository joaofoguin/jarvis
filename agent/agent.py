import os
import time
import subprocess
import requests

from dotenv import load_dotenv


load_dotenv()

JARVIS_URL = "https://jarvis-one-opal-45.vercel.app"

AGENT_TOKEN = os.getenv("AGENT_TOKEN")


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


def execute_command(command_id, command_text):

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
