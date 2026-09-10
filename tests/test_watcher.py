import json

import pytest

from cgv_alarm import watcher


def rec(seats, key_tm="1800", cntl="N", **over):
    r = {
        "siteNo": "0013",
        "siteNm": "CGV 용산아이파크몰",
        "scnYmd": "20260912",
        "scnsNo": "018",
        "scnsNm": "IMAX관",
        "scnSseq": "4",
        "scnsrtTm": key_tm,
        "movNo": "30001323",
        "movNm": "오디세이",
        "frSeatCnt": str(seats),
        "frtmpSeatCnt": str(seats),
        "stcnt": "624",
        "cntlYn": cntl,
        "bzplcNo": "0013001",
    }
    r.update(over)
    return r


CONFIG = {"watches": [{"site_no": "0013", "mov_no": "30001323", "dates": ["20260912"]}]}
SCOPES = ["0013:20260912:30001323"]


def run(monkeypatch, state, records, scopes=SCOPES):
    monkeypatch.setattr(watcher, "fetch_watch", lambda w: (records, scopes))
    return watcher.run_check(CONFIG, state)


def test_first_observation_no_alert(monkeypatch):
    state = {}
    alerts, errors = run(monkeypatch, state, [rec(0)])
    assert alerts == [] and errors == []
    assert list(state["shows"].values()) == [{"frSeatCnt": 0}]


def test_soldout_to_available_alerts(monkeypatch):
    state = {}
    run(monkeypatch, state, [rec(0)])
    alerts, _ = run(monkeypatch, state, [rec(3)])
    assert len(alerts) == 1 and alerts[0]["frSeatCnt"] == "3"


def test_available_increase_no_alert(monkeypatch):
    state = {}
    run(monkeypatch, state, [rec(3)])
    alerts, _ = run(monkeypatch, state, [rec(5)])
    assert alerts == []


def test_no_realert_while_available(monkeypatch):
    state = {}
    run(monkeypatch, state, [rec(0)])
    run(monkeypatch, state, [rec(2)])  # 알림 1회
    alerts, _ = run(monkeypatch, state, [rec(2)])
    assert alerts == []


def test_realert_after_resoldout(monkeypatch):
    state = {}
    run(monkeypatch, state, [rec(0)])
    run(monkeypatch, state, [rec(1)])
    run(monkeypatch, state, [rec(0)])  # 재매진
    alerts, _ = run(monkeypatch, state, [rec(1)])
    assert len(alerts) == 1


def test_controlled_show_no_alert(monkeypatch):
    # cntlYn=Y는 판매통제 → 0에서 풀려도 통제 중이면 알림 금지
    state = {}
    run(monkeypatch, state, [rec(0, cntl="Y")])
    alerts, _ = run(monkeypatch, state, [rec(134, cntl="Y")])
    assert alerts == []


def test_disappeared_show_pruned(monkeypatch):
    state = {}
    run(monkeypatch, state, [rec(0), rec(0, key_tm="2100")])
    run(monkeypatch, state, [rec(0, key_tm="2100")])
    assert len(state["shows"]) == 1


def test_fetch_error_keeps_state(monkeypatch):
    state = {}
    run(monkeypatch, state, [rec(0)])

    def boom(w):
        raise watcher.api.ApiError("HTTP 403")

    monkeypatch.setattr(watcher, "fetch_watch", boom)
    alerts, errors = watcher.run_check(CONFIG, state)
    assert alerts == [] and len(errors) == 1
    assert len(state["shows"]) == 1  # 실패 시 기존 회차 유지


def test_fail_alert_after_threshold(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(watcher.notify, "send_all", lambda t: sent.append(t) or True)
    monkeypatch.setattr(watcher, "run_check", lambda c, s: ([], ["HTTP 403"]))
    state_path = tmp_path / "state.json"
    config_path = tmp_path / "config.yaml"
    config_path.write_text("watches: []\n")
    for _ in range(4):
        watcher.check_once(config_path, state_path)
    assert len(sent) == 1 and "실패" in sent[0]
    # 복구되면 카운터 리셋
    monkeypatch.setattr(watcher, "run_check", lambda c, s: ([], []))
    watcher.check_once(config_path, state_path)
    st = json.loads(state_path.read_text())
    assert st["fail_count"] == 0 and st["fail_alerted"] is False


def test_format_time_over_24h():
    assert watcher.format_time("2500") == "익일 01:00"
    assert watcher.format_time("1830") == "18:30"


MOVIES = [{"movNo": "30009999", "movNm": "아바타: 새로운 시대", "atktRate": "31.2"}]


def test_open_check_fires_and_removes(monkeypatch):
    monkeypatch.setattr(watcher.api, "movies_on_sale", lambda: MOVIES)
    config = {"opens": [{"query": "아바타"}, {"query": "안나오는영화"}]}
    msgs, errors, changed = watcher.run_open_check(config, {})
    assert len(msgs) == 1 and "예매 오픈" in msgs[0] and "아바타" in msgs[0]
    assert changed and config["opens"] == [{"query": "안나오는영화"}]
    assert errors == []


def test_open_check_no_match_keeps(monkeypatch):
    monkeypatch.setattr(watcher.api, "movies_on_sale", lambda: MOVIES)
    config = {"opens": [{"query": "듄3"}]}
    msgs, errors, changed = watcher.run_open_check(config, {})
    assert msgs == [] and not changed and len(config["opens"]) == 1


def test_open_check_site_scoped(monkeypatch):
    monkeypatch.setattr(watcher.api, "movies_on_sale", lambda: MOVIES)
    monkeypatch.setattr(watcher.api, "open_dates", lambda site: ["20260920"])
    monkeypatch.setattr(
        watcher.api,
        "schedule_by_movie",
        lambda site, ymd, mov: [{"scnYmd": ymd, "scnsrtTm": "1500", "scnsNm": "IMAX관", "bzplcNo": "0013001"}],
    )
    config = {"opens": [{"query": "아바타", "site_no": "0013", "site_nm": "용산아이파크몰"}]}
    msgs, _, changed = watcher.run_open_check(config, {})
    assert changed and "용산아이파크몰" in msgs[0] and "15:00" in msgs[0]


def test_open_check_api_error_keeps_all(monkeypatch):
    def boom():
        raise watcher.api.ApiError("HTTP 403")
    monkeypatch.setattr(watcher.api, "movies_on_sale", boom)
    config = {"opens": [{"query": "아바타"}]}
    msgs, errors, changed = watcher.run_open_check(config, {})
    assert msgs == [] and len(errors) == 1 and not changed


def test_open_check_normalized_title(monkeypatch):
    # 띄어쓰기/콜론이 달라도 매칭
    monkeypatch.setattr(watcher.api, "movies_on_sale", lambda: MOVIES)
    config = {"opens": [{"query": "아바타 새로운시대"}]}
    msgs, _, changed = watcher.run_open_check(config, {})
    assert changed and "예매 오픈" in msgs[0]


def test_open_check_fuzzy_typo_notifies_once(monkeypatch):
    # "새로온"(오타) → 자동 발화는 안 하지만 유사 제목 안내는 1회 발송
    monkeypatch.setattr(watcher.api, "movies_on_sale", lambda: MOVIES)
    config = {"opens": [{"query": "아바타 새로온 시대"}]}
    state = {}
    msgs, _, changed = watcher.run_open_check(config, state)
    assert not changed and len(msgs) == 1 and "비슷한 제목" in msgs[0]
    msgs2, _, _ = watcher.run_open_check(config, state)
    assert msgs2 == []  # 같은 후보로 재알림 없음
