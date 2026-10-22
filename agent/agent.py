import time
import subprocess
import requests


JARVIS_URL = "https://jarvis-one-opal-45.vercel.app"


def complete_command(command_id):
    response = requests.post(
        f"{JARVIS_URL}/agent/commands/{command_id}/complete",
        json={},
        timeout=10
    )

    response.raise_for_status()

    result = response.json()

    if result.get("success"):
        print(f"[COMANDO CONCLUÍDO] ID={command_id}")


def execute_command(command_id, command_text):

    if command_text == "open_app:notepad":
        print("[AÇÃO] Abrindo Bloco de Notas...")

        subprocess.Popen(["notepad.exe"])

        complete_command(command_id)

    elif command_text == "open_website:whatsapp":
        print("[AÇÃO] Abrindo WhatsApp Web...")

        subprocess.Popen([
            "cmd",
            "/c",
            "start",
            "",
            "https://web.whatsapp.com"
        ])

        complete_command(command_id)

    else:
        print(f"[AVISO] Comando não autorizado: {command_text}")


def check_commands():

    response = requests.get(
        f"{JARVIS_URL}/agent/commands",
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