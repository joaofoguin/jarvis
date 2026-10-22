from datetime import date, datetime, timedelta

import pytest

import icloud_data


AMOR = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Amor\r\nitem1.TEL;type=CELL;type=pref:+55 43 99999-0000\r\nEND:VCARD"
AMORIM = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Pedro\r\n  Amorim\r\nTEL:tel:+5543988887777\r\nTEL;type=WORK:3333-4444\r\nEND:VCARD"
SEM_TELEFONE = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ana Amor\r\nEND:VCARD"


def test_parse_card_reads_name_and_phones():
    assert icloud_data.parse_card(AMOR) == ("Amor", ["+55 43 99999-0000"])
    assert icloud_data.parse_card(AMORIM) == ("Pedro Amorim", ["+5543988887777", "3333-4444"])


def test_exact_name_hides_partial_matches():
    found = icloud_data.find_contacts("amor", [AMORIM, SEM_TELEFONE, AMOR])

    assert [name for name, _ in found] == ["Amor"]


def test_partial_matches_when_no_exact_name():
    found = icloud_data.find_contacts("amor", [AMORIM, SEM_TELEFONE])

    assert [name for name, _ in found] == ["Pedro Amorim", "Ana Amor"]


def test_contact_summary():
    assert icloud_data.contact_summary("Amor", [AMOR, SEM_TELEFONE]) == "Contatos encontrados:\n- Amor: +55 43 99999-0000"
    assert icloud_data.contact_summary("Ana", [AMOR, SEM_TELEFONE]) == "Contatos encontrados:\n- Ana Amor: sem telefone"
    assert icloud_data.contact_summary("Zé", [AMOR]) == "Não encontrei Zé nos seus contatos do iCloud, senhor."


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("ICLOUD_EMAIL", raising=False)

    with pytest.raises(RuntimeError, match="ICLOUD_EMAIL"):
        icloud_data.credentials()


class FakeResponse:
    def __init__(self, body, status_code=207):
        self.content = body.encode()
        self.status_code = status_code

    def raise_for_status(self):
        pass


def multistatus(inner):
    return f'<d:multistatus xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">{inner}</d:multistatus>'


def test_address_cards_follows_icloud_discovery(monkeypatch):
    monkeypatch.setenv("ICLOUD_EMAIL", "eu@icloud.com")
    monkeypatch.setenv("ICLOUD_APP_PASSWORD", "abcd-efgh-ijkl-mnop")
    calls = []

    replies = [
        multistatus("<d:response><d:propstat><d:prop><d:current-user-principal><d:href>/123/principal/</d:href>"
                    "</d:current-user-principal></d:prop></d:propstat></d:response>"),
        multistatus("<d:response><d:propstat><d:prop><card:addressbook-home-set>"
                    "<d:href>https://p01-contacts.icloud.com/123/carddav/</d:href>"
                    "</card:addressbook-home-set></d:prop></d:propstat></d:response>"),
        multistatus("<d:response><d:href>/123/carddav/</d:href><d:propstat><d:prop><d:resourcetype>"
                    "<d:collection/></d:resourcetype></d:prop></d:propstat></d:response>"
                    "<d:response><d:href>/123/carddav/card/</d:href><d:propstat><d:prop><d:resourcetype>"
                    "<d:collection/><card:addressbook/></d:resourcetype></d:prop></d:propstat></d:response>"),
        multistatus(f"<d:response><d:propstat><d:prop><card:address-data>{AMOR}</card:address-data>"
                    "</d:prop></d:propstat></d:response>"),
    ]

    def request(method, url, **kwargs):
        calls.append((method, url))
        return FakeResponse(replies[len(calls) - 1])

    monkeypatch.setattr(icloud_data.requests, "request", request)

    assert [icloud_data.parse_card(card)[0] for card in icloud_data.address_cards()] == ["Amor"]
    assert calls[-1] == ("REPORT", "https://p01-contacts.icloud.com/123/carddav/card/")


def test_wrong_password_gives_clear_error(monkeypatch):
    monkeypatch.setenv("ICLOUD_EMAIL", "eu@icloud.com")
    monkeypatch.setenv("ICLOUD_APP_PASSWORD", "errada")
    monkeypatch.setattr(icloud_data.requests, "request", lambda *args, **kwargs: FakeResponse("", 401))

    with pytest.raises(RuntimeError, match="senha de app"):
        icloud_data.address_cards()


class FakeEvent:
    def __init__(self, start, summary):
        self.icalendar_component = {"dtstart": type("Prop", (), {"dt": start})(), "summary": summary}


class FakeCalendar:
    name = "Casa"

    def __init__(self, events):
        self.events = events

    def search(self, **kwargs):
        assert kwargs["event"] and kwargs["expand"]
        return self.events


def test_agenda_summary_sorts_events_from_all_calendars():
    today = datetime.now().astimezone().replace(hour=15, minute=0, second=0, microsecond=0)
    calendars = [
        FakeCalendar([FakeEvent(today, "Dentista")]),
        FakeCalendar([FakeEvent(today.date(), "Aniversário da Amor")]),
    ]

    assert icloud_data.agenda_summary(1, calendars) == (
        f"Calendário do iCloud hoje:\n- {today:%d/%m} (dia todo) Aniversário da Amor\n- {today:%d/%m} 15:00 Dentista"
    )


def test_agenda_summary_when_empty():
    assert icloud_data.agenda_summary(7, [FakeCalendar([])]) == "Nada no calendário do iCloud nos próximos 7 dias, senhor."
