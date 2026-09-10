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
    for _ in range(4):
        watcher.check_once({}, state_path)
    assert len(sent) == 1 and "실패" in sent[0]
    # 복구되면 카운터 리셋
    monkeypatch.setattr(watcher, "run_check", lambda c, s: ([], []))
    watcher.check_once({}, state_path)
    st = json.loads(state_path.read_text())
    assert st["fail_count"] == 0 and st["fail_alerted"] is False


def test_format_time_over_24h():
    assert watcher.format_time("2500") == "익일 01:00"
    assert watcher.format_time("1830") == "18:30"
