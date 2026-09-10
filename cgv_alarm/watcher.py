"""매진 회차의 취소표(frSeatCnt 0 → 양수) 전환 감지.

1회 실행 → 상태 비교 → 알림 → 상태 저장 후 종료하는 구조.
GitHub Actions cron이 반복시키고, VPS/로컬에서는 loop 명령이 감싼다.
"""

import json
import time
from pathlib import Path

from . import api, configfile, notify

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


def _check_open_watch(ow: dict, movies: list[dict]):
    """오픈 감시 1건 판정 → (발화 여부, 알림 문구). movies는 예매 중 영화 목록."""
    matches = [m for m in movies if ow["query"] in m["movNm"]]
    if not matches:
        return False, ""
    if not ow.get("site_no"):
        m = matches[0]
        rate = f" · 예매율 {m['atktRate']}%" if m.get("atktRate") else ""
        return True, (
            f"🎟 예매 오픈!\n{m['movNm']}{rate}\nhttps://cgv.co.kr\n"
            "(이 오픈 알림은 자동 해제됐어요. 원하는 회차가 매진되면 /watch로 취소표 감시를 등록하세요.)"
        )
    # 극장 한정: 그 극장 시간표에 해당 영화 회차가 뜨는지
    site = str(ow["site_no"])
    for m in matches:
        for ymd in api.open_dates(site):
            recs = api.schedule_by_movie(site, ymd, m["movNo"])
            if recs:
                r = recs[0]
                return True, (
                    f"🎟 예매 오픈!\n{m['movNm']} · CGV {ow.get('site_nm', site)}\n"
                    f"첫 회차: {format_date(r['scnYmd'])} {format_time(r['scnsrtTm'])} {r['scnsNm']}\n"
                    f"예매: https://cgv.co.kr/cnm/bzplcCgv/{r['bzplcNo']}\n"
                    "(이 오픈 알림은 자동 해제됐어요.)"
                )
            time.sleep(0.3)
    return False, ""


def run_open_check(config: dict):
    """오픈 감시 전체 판정 → (알림 문구들, 오류들, config 변경 여부).

    발화한 오픈 감시는 일회성이므로 config에서 제거된다.
    """
    opens = config.get("opens") or []
    if not opens:
        return [], [], False
    try:
        movies = api.movies_on_sale()
    except Exception as e:
        return [], [f"오픈 감시 조회 실패: {e}"], False
    msgs, errors, remaining = [], [], []
    for ow in opens:
        try:
            fired, msg = _check_open_watch(ow, movies)
        except Exception as e:
            errors.append(f"오픈 감시 '{ow.get('query')}': {e}")
            remaining.append(ow)
            continue
        (msgs if fired else remaining).append(msg if fired else ow)
    if len(remaining) != len(opens):
        config["opens"] = remaining
        return msgs, errors, True
    return msgs, errors, False


def check_once(config_path: Path, state_path: Path) -> int:
    """1회 체크. 반환값은 프로세스 종료 코드."""
    config = configfile.load(config_path)
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

    open_msgs, open_errors, config_changed = run_open_check(config)
    errors.extend(open_errors)
    for msg in open_msgs:
        print(f"[watcher] 예매 오픈 감지! {msg.splitlines()[1]}")
        notify.send_all(msg)
    if config_changed:
        configfile.save(config_path, config)  # 발화한 오픈 감시 자동 해제

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
        f"[watcher] 감시 중 {len(shows)}개 회차 (매진 {sold_out}) + 오픈 대기 "
        f"{len(config.get('opens') or [])}건, 알림 {len(alerts) + len(open_msgs)}건, 오류 {len(errors)}건"
    )
    return 0
