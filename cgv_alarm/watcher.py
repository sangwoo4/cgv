"""매진 회차의 취소표(frSeatCnt 0 → 양수) 전환 감지.

1회 실행 → 상태 비교 → 알림 → 상태 저장 후 종료하는 구조.
GitHub Actions cron이 반복시키고, VPS/로컬에서는 loop 명령이 감싼다.
"""

import json
import time
from pathlib import Path

from . import api, notify

FAIL_ALERT_THRESHOLD = 3  # 연속 실패 이 횟수부터 장애 알림 1회


def show_key(rec: dict) -> str:
    # scnSseq는 회차 추가 시 재배치되므로 키로 쓰지 않는다
    return ":".join(
        [rec["siteNo"], rec["scnYmd"], rec["scnsNo"], rec["scnsrtTm"], rec["movNo"]]
    )


def format_time(tm: str) -> str:
    # scnsrtTm은 "2500"(익일 01:00)처럼 24시를 초과할 수 있다
    hh, mm = int(tm[:2]), tm[2:]
    return f"익일 {hh - 24:02d}:{mm}" if hh >= 24 else f"{hh:02d}:{mm}"


def format_date(ymd: str) -> str:
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"


def alert_message(rec: dict) -> str:
    extra = ""
    try:
        tmp = int(rec.get("frtmpSeatCnt", 0)) - int(rec.get("frSeatCnt", 0))
        if tmp > 0:
            extra = f" (+선점 중 {tmp}석)"
    except ValueError:
        pass
    return "\n".join(
        [
            "🎬 취소표 발견!",
            f"{rec['movNm']} · {rec['scnsNm']}",
            rec["siteNm"],
            f"{format_date(rec['scnYmd'])} {format_time(rec['scnsrtTm'])} 시작",
            f"잔여 {rec['frSeatCnt']}석{extra}",
            f"예매: https://cgv.co.kr/cnm/bzplcCgv/{rec['bzplcNo']}",
        ]
    )


def fetch_watch(watch: dict) -> tuple[list[dict], list[str]]:
    """watch 하나의 회차 레코드들과, 성공적으로 조회한 scope 목록을 반환."""
    site_no = str(watch["site_no"])
    mov_no = watch.get("mov_no")
    dates = [str(d) for d in watch.get("dates") or api.open_dates(site_no)]
    records: list[dict] = []
    scopes: list[str] = []
    for ymd in dates:
        if mov_no:
            recs = api.schedule_by_movie(site_no, ymd, str(mov_no))
        else:
            recs = api.schedule_all(site_no, ymd)
        if times := watch.get("times"):
            times = [str(t) for t in times]
            recs = [r for r in recs if r["scnsrtTm"] in times]
        records.extend(recs)
        scopes.append(f"{site_no}:{ymd}:{mov_no or '*'}")
        time.sleep(0.5)
    return records, scopes


def run_check(config: dict, state: dict) -> tuple[list[dict], list[str]]:
    """state를 제자리 갱신하고 (알림 대상 레코드, 오류 메시지) 반환."""
    shows: dict = state.setdefault("shows", {})
    observed: dict[str, dict] = {}
    fetched_scopes: list[str] = []
    errors: list[str] = []

    for watch in config.get("watches") or []:
        try:
            records, scopes = fetch_watch(watch)
            fetched_scopes.extend(scopes)
            for rec in records:
                observed[show_key(rec)] = rec
        except Exception as e:
            errors.append(f"watch {watch.get('site_no')}/{watch.get('mov_no', '*')}: {e}")

    alerts: list[dict] = []
    for key, rec in observed.items():
        try:
            cnt = int(rec.get("frSeatCnt"))
        except (TypeError, ValueError):
            errors.append(f"frSeatCnt 파싱 불가: {key}")
            continue
        prev = shows.get(key)
        if (
            prev is not None
            and prev.get("frSeatCnt") == 0
            and cnt > 0
            and rec.get("cntlYn") == "N"
        ):
            alerts.append(rec)
        shows[key] = {"frSeatCnt": cnt}

    # 조회에 성공한 scope에서 사라진 회차(상영 시작/취소)는 state에서 제거
    def covered(key: str) -> bool:
        site, ymd, _scns, _tm, mov = key.split(":")
        return any(s in (f"{site}:{ymd}:{mov}", f"{site}:{ymd}:*") for s in fetched_scopes)

    for key in [k for k in shows if k not in observed and covered(k)]:
        del shows[key]

    return alerts, errors


def check_once(config: dict, state_path: Path) -> int:
    """1회 체크. 반환값은 프로세스 종료 코드."""
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except ValueError:
            print(f"[watcher] state 파일 손상, 초기화: {state_path}")

    alerts, errors = run_check(config, state)

    for rec in alerts:
        msg = alert_message(rec)
        print(f"[watcher] 취소표! {show_key(rec)} → {rec['frSeatCnt']}석")
        notify.send_all(msg)

    if errors:
        state["fail_count"] = state.get("fail_count", 0) + 1
        print(f"[watcher] 조회 실패 {state['fail_count']}회 연속: {errors}")
        if state["fail_count"] >= FAIL_ALERT_THRESHOLD and not state.get("fail_alerted"):
            notify.send_all(
                "⚠️ CGV 알람: 조회가 계속 실패하고 있어요. 점검이 필요합니다.\n" + errors[0]
            )
            state["fail_alerted"] = True
    else:
        state["fail_count"] = 0
        state["fail_alerted"] = False

    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1))

    shows = state.get("shows", {})
    sold_out = sum(1 for s in shows.values() if s["frSeatCnt"] == 0)
    print(
        f"[watcher] 감시 중 {len(shows)}개 회차 (매진 {sold_out}), "
        f"알림 {len(alerts)}건, 오류 {len(errors)}건"
    )
    return 0
