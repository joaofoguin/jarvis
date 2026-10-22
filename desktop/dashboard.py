"""O painel lateral do chat em tela cheia: agenda, Classroom, notícias, histórico e uso de IA.

Cada parte é carregada separadamente, para uma lenta ou com erro não segurar as outras.
"""

import json
import os
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

import requests

import google_data
from desktop import core, settings, usage


NEWS_PER_TOPIC = 4
NEWS_TIMEOUT = 10

HISTORY_SHOWN = 8

# Guarda só o começo de cada resposta; o histórico é para lembrar o que foi pedido.
HISTORY_ANSWER_LIMIT = 200


def history_path():
    return Path(os.getenv("JARVIS_HISTORY") or Path.home() / ".jarvis" / "historico.jsonl")


def log(when, text, answer):
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"when": when.isoformat(timespec="minutes"), "text": text, "answer": answer[:HISTORY_ANSWER_LIMIT]}

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def history():
    path = history_path()

    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()[-HISTORY_SHOWN:]
    return [json.loads(line) for line in reversed(lines)]


def google_ready():
    # Só consulta o Google se o login já foi feito; o painel nunca abre o navegador sozinho.
    return all(os.path.exists(google_data.token_file(account)) for account in google_data.accounts())


def agenda():
    if not google_ready():
        return "Peça \"minha agenda\" no chat uma vez para entrar no Google."

    return core.agenda(1, "")


def classroom():
    if not google_ready():
        return "Peça \"minhas tarefas do Classroom\" no chat uma vez para entrar no Google."

    return core.run_google(google_data.classroom_summary, None, "")


def news_url(topic):
    return f"https://news.google.com/rss/search?q={quote(topic)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"


def parse_news(xml_text, topic):
    items = []

    for item in list(ET.fromstring(xml_text).iter("item"))[:NEWS_PER_TOPIC]:
        published = item.findtext("pubDate")
        items.append({
            "topic": topic,
            "title": item.findtext("title", ""),
            "link": item.findtext("link", ""),
            "source": item.findtext("source", ""),
            "when": parsedate_to_datetime(published).isoformat() if published else ""
        })

    return items


def news():
    """Notícias dos temas escolhidos nas preferências, das mais novas para as mais antigas."""

    found = []
    seen = set()

    for topic in settings.load()["news_topics"]:
        response = requests.get(news_url(topic), timeout=NEWS_TIMEOUT)
        response.raise_for_status()

        for item in parse_news(response.text, topic):
            if item["link"] not in seen:
                seen.add(item["link"])
                found.append(item)

    return sorted(found, key=lambda item: item["when"], reverse=True)


def usage_today():
    today = usage.summarize(usage.rows(days=1), date.today(), days=1)
    return {"tokens": today["total"], "calls": today["calls"], "cost": today["cost"]}


SECTIONS = {
    "agenda": agenda,
    "classroom": classroom,
    "news": news,
    "history": history,
    "usage": usage_today
}


def load(section):
    try:
        return {"ok": SECTIONS[section]()}

    except Exception as error:
        return {"error": str(error)}
