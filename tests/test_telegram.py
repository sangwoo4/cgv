import datetime

import pytest

from cgv_alarm import telegram

TODAY = datetime.date(2026, 9, 10)


@pytest.fixture
def fake_lookup(monkeypatch):
    monkeypatch.setattr(
        telegram.watcher,
        "fetch_watch",
        lambda w: ([{"scnYmd": "20260912", "scnsrtTm": "1800", "scnsNm": "IMAX관", "frSeatCnt": "0"}], ["scope"]),
    )
    monkeypatch.setattr(
        telegram.lookup,
        "find_theaters",
        lambda q: [{"siteNo": "0013", "siteNm": "용산아이파크몰"}] if "용산" in q else [],
    )
    monkeypatch.setattr(
        telegram.lookup,
        "find_movies",
        lambda q: [{"movNo": "30001323", "movNm": "오디세이"}] if "오디세이" in q else [],
    )


def test_watch_full(fake_lookup):
    config = {"watches": []}
    reply, changed = telegram.handle_command("/watch 용산 오디세이 0912 18:00", config, TODAY)
    assert changed
    w = config["watches"][0]
    assert w["site_no"] == "0013" and w["mov_no"] == "30001323"
    assert w["dates"] == ["20260912"] and w["times"] == ["1800"]
    assert "등록했어요" in reply


def test_watch_past_mmdd_rolls_to_next_year(fake_lookup):
    config = {"watches": []}
    telegram.handle_command("/watch 용산 오디세이 0101", config, TODAY)
    assert config["watches"][0]["dates"] == ["20270101"]


def test_watch_theater_only(fake_lookup):
    config = {"watches": None}  # yaml에서 watches: 빈 값인 경우
    reply, changed = telegram.handle_command("/watch 용산", config, TODAY)
    assert changed and "mov_no" not in config["watches"][0]
    assert "전체 영화" in reply


def test_watch_unknown_theater(fake_lookup):
    config = {"watches": []}
    reply, changed = telegram.handle_command("/watch 없는극장", config, TODAY)
    assert not changed and "못 찾았어요" in reply


def test_watch_duplicate(fake_lookup):
    config = {"watches": []}
    telegram.handle_command("/watch 용산 오디세이", config, TODAY)
    reply, changed = telegram.handle_command("/watch 용산 오디세이", config, TODAY)
    assert not changed and "이미" in reply and len(config["watches"]) == 1


def test_list_and_remove(fake_lookup):
    config = {"watches": []}
    telegram.handle_command("/watch 용산 오디세이 0912", config, TODAY)
    reply, _ = telegram.handle_command("/list", config, TODAY)
    assert "1." in reply and "오디세이" in reply and "09/12" in reply
    reply, changed = telegram.handle_command("/remove 1", config, TODAY)
    assert changed and config["watches"] == []
    reply, _ = telegram.handle_command("/remove 1", config, TODAY)
    assert "번호" in reply


def test_help_and_unknown(fake_lookup):
    config = {}
    for text in ("/start", "/help", "/뭐야"):
        reply, changed = telegram.handle_command(text, config, TODAY)
        assert not changed and "/watch" in reply


def test_command_with_botname_suffix(fake_lookup):
    config = {"watches": []}
    reply, _ = telegram.handle_command("/list@cgv_alarm_bot", config, TODAY)
    assert "감시" in reply


def test_watch_reply_lists_matching_shows(fake_lookup):
    config = {"watches": []}
    reply, _ = telegram.handle_command("/watch 용산 오디세이 0912 18:00", config, TODAY)
    assert "매칭 회차 1개" in reply and "매진" in reply


def test_watch_reply_warns_when_no_match(fake_lookup, monkeypatch):
    monkeypatch.setattr(telegram.watcher, "fetch_watch", lambda w: ([], ["scope"]))
    config = {"watches": []}
    reply, changed = telegram.handle_command("/watch 용산 오디세이 0912 07:77", config, TODAY)
    assert changed and "⚠️" in reply


def test_command_without_slash(fake_lookup):
    config = {"watches": []}
    reply, changed = telegram.handle_command("watch 용산 오디세이", config, TODAY)
    assert changed and "등록했어요" in reply
    reply, _ = telegram.handle_command("list", config, TODAY)
    assert "1." in reply


def test_normalize_cmd():
    assert telegram._normalize_cmd("/watch@cgv_sw_bot 용산") == "watch"
    assert telegram._normalize_cmd("WATCH 용산") == "watch"
    assert telegram._normalize_cmd("아무말") == "아무말"
