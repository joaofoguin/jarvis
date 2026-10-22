from datetime import datetime

import pytest

from desktop import dashboard, settings


RSS = """<?xml version="1.0"?>
<rss><channel>
  <item><title>IA nova lançada</title><link>https://exemplo.com/a</link><pubDate>Wed, 22 Oct 2026 12:00:00 GMT</pubDate><source url="x">Jornal A</source></item>
  <item><title>Chip mais rápido</title><link>https://exemplo.com/b</link><pubDate>Wed, 22 Oct 2026 15:00:00 GMT</pubDate><source url="y">Jornal B</source></item>
</channel></rss>"""


def test_parse_news_reads_title_link_source_and_time():
    items = dashboard.parse_news(RSS, "tecnologia")

    assert items[0] == {
        "topic": "tecnologia",
        "title": "IA nova lançada",
        "link": "https://exemplo.com/a",
        "source": "Jornal A",
        "when": "2026-10-22T12:00:00+00:00"
    }


class FakeResponse:
    text = RSS

    def raise_for_status(self):
        pass


def test_news_follows_saved_topics_without_repeats(monkeypatch):
    settings.save({"news_topics": ["tecnologia", "inteligência artificial"]})
    asked = []
    monkeypatch.setattr(dashboard.requests, "get", lambda url, timeout: asked.append(url) or FakeResponse())

    items = dashboard.news()

    assert asked == [dashboard.news_url("tecnologia"), dashboard.news_url("inteligência artificial")]
    assert "intelig%C3%AAncia%20artificial" in asked[1]
    assert [item["title"] for item in items] == ["Chip mais rápido", "IA nova lançada"]


def test_history_shows_latest_first_with_short_answers():
    for n in range(dashboard.HISTORY_SHOWN + 2):
        dashboard.log(datetime(2026, 10, 22, 9, n), f"pedido {n}", "x" * 500)

    entries = dashboard.history()

    assert len(entries) == dashboard.HISTORY_SHOWN
    assert entries[0]["text"] == f"pedido {dashboard.HISTORY_SHOWN + 1}"
    assert entries[0]["when"] == f"2026-10-22T09:{dashboard.HISTORY_SHOWN + 1:02d}"
    assert len(entries[0]["answer"]) == dashboard.HISTORY_ANSWER_LIMIT


def test_agenda_never_opens_google_login_from_the_dashboard(monkeypatch):
    monkeypatch.setattr(dashboard.google_data, "accounts", lambda: ["eu@gmail.com"])
    monkeypatch.setattr(dashboard.core, "agenda", lambda days, text: pytest.fail("não deveria consultar"))

    assert "minha agenda" in dashboard.agenda()


def test_failing_section_reports_error():
    assert dashboard.load("desconhecida") == {"error": "'desconhecida'"}


@pytest.mark.parametrize("topics", [["x" * 61], [""], ["a"] * 11, "tecnologia"])
def test_invalid_news_topics_are_refused(topics):
    with pytest.raises(ValueError):
        settings.save({"news_topics": topics})


def test_news_topics_are_cleaned_and_deduplicated():
    assert settings.save({"news_topics": ["  vagas   de TI ", "vagas de TI", "Bauru"]})["news_topics"] == ["vagas de TI", "Bauru"]
