"""Confere, logo depois que o app abre, se os logins salvos ainda valem. Nunca abre o navegador."""

import os

import drive_data
import google_data
import icloud_data
from desktop import notices


# (tipo do login, permissões, nome mostrado, como refazer o login)
GOOGLE_LOGINS = [
    ("", google_data.SCOPES, "agenda e Classroom", "peça \"minha agenda\" no chat"),
    (drive_data.KIND, drive_data.SCOPES, "Drive", "peça uma busca no Drive pelo chat"),
    (notices.KIND, notices.SCOPES, "mural", "use \"Conectar\" no mural, nas preferências"),
    ("youtube", google_data.YOUTUBE_SCOPES, "YouTube", "peça as métricas do YouTube no chat")
]


def check():
    """Retorna (quantos funcionam, avisos). Só confere os logins que já foram feitos alguma vez."""

    working = 0
    problems = []

    for account in google_data.accounts():
        for kind, scopes, name, how in GOOGLE_LOGINS:
            if not os.path.exists(google_data.token_file(account, kind)):
                continue

            label = f"{name} de {account or 'sua conta'}"

            try:
                google_data.get_credentials(account, scopes, kind, interactive=False)
                working += 1

            except google_data.LoginNeeded:
                problems.append(f"{label}: o login venceu; {how}.")

            except Exception as error:
                problems.append(f"{label}: não consegui conferir ({error}).")

    if icloud_data.configured():
        try:
            icloud_data.carddav("PROPFIND", icloud_data.CARDDAV_URL, icloud_data.PRINCIPAL_BODY, "0")
            working += 1

        except Exception as error:
            problems.append(f"iCloud: {error}.")

    return working, problems


def report(working, problems):
    """Texto para o chat, ou None se não há nenhuma conexão configurada."""

    if problems:
        return "Conexões com problema:\n" + "\n".join(f"- {problem}" for problem in problems)

    if working:
        return f"Conexões conferidas: {working} funcionando."

    return None
