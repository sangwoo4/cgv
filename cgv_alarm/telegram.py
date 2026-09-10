"""텔레그램 봇 명령 처리: /watch /open /list /remove /help

봇이 상주하지 않는 구조(Actions cron)라 매 실행마다 getUpdates로 밀린
명령을 모아 처리한다. 응답은 다음 cron 주기(최대 5~10분)에 도착한다.
명령으로 바뀐 감시 대상은 config.yaml에 저장되고 워크플로가 커밋한다.
"""

import datetime
import json
import os
from pathlib import Path

import requests
from . import configfile, lookup, watcher

HELP = """CGV 취소표 알람 봇 명령:

/watch 극장 [영화] [날짜] [시간] — 감시 등록
  예: /watch 용산 오디세이 0912 18:00
  날짜는 0912 또는 20260912, 시간은 18:00 형식 (여러 개 가능)
  영화 생략 시 극장 전체, 날짜 생략 시 예매 오픈된 전 날짜
/open 영화 — 예매 오픈 알림 (아직 예매 안 열린 영화)
  예: /open 아바타
  극장을 먼저 쓰면 그 극장 한정: /open 용산아이파크몰 아바타
  오픈 알림은 한 번 울리면 자동 해제돼요
/list — 감시 목록
/remove 번호 — 감시 해제 (/list에 나온 번호)
/help — 이 도움말

명령 처리는 최대 5~10분 걸릴 수 있어요.
매진 회차에 취소표가 나오면 바로 알려드립니다."""

def _expand_date(mmdd: str, today: datetime.date) -> str:
    """MMDD → YYYYMMDD. 이미 지난 날짜면 내년으로 해석."""
    d = f"{today.year}{mmdd}"
    return f"{today.year + 1}{mmdd}" if d < today.strftime("%Y%m%d") else d


def _parse_watch_args(tokens: list[str], today: datetime.date):
    """토큰을 (이름 단어들, 날짜들, 시간들)로 분류.

    콜론 포함(18:00) → 시간, 8자리 숫자 → 날짜, 4자리 숫자 → MMDD 날짜.
    """
    words, dates, times = [], [], []
    for t in tokens:
        if ":" in t:
            hhmm = t.replace(":", "")
            if hhmm.isdigit() and len(hhmm) == 4:
                times.append(hhmm)
                continue
        if t.isdigit() and len(t) == 8:
            dates.append(t)
            continue
        if t.isdigit() and len(t) == 4:
            dates.append(_expand_date(t, today))
            continue
        words.append(t)
    return words, dates, times


def _watch_label(w: dict) -> str:
    parts = [f"CGV {w.get('site_nm', w['site_no'])}", w.get("mov_nm") or ("전체 영화" if not w.get("mov_no") else str(w["mov_no"]))]
    if w.get("dates"):
        parts.append(",".join(f"{d[4:6]}/{d[6:]}" for d in map(str, w["dates"])))
    if w.get("times"):
        parts.append(",".join(f"{t[:2]}:{t[2:]}" for t in map(str, w["times"])))
    return " · ".join(parts)


def _cmd_watch(tokens: list[str], config: dict, today: datetime.date):
    words, dates, times = _parse_watch_args(tokens, today)
    if not words:
        return "극장 이름이 필요해요. 예: /watch 용산 오디세이 0912 18:00", False

    theater_q, movie_q = words[0], " ".join(words[1:]) or None
    sites = lookup.find_theaters(theater_q)
    if not sites:
        return f"'{theater_q}' 극장을 못 찾았어요.", False
    if len(sites) > 1:
        opts = "\n".join(f"- {s['siteNm']}" for s in sites[:10])
        return f"극장이 여러 개 검색돼요. 더 정확히 써주세요:\n{opts}", False
    site = sites[0]

    watch = {"site_no": site["siteNo"], "site_nm": site["siteNm"]}
    movie_label = "전체 영화"
    if movie_q:
        movies = lookup.find_movies(movie_q)
        if not movies:
            return f"'{movie_q}' 영화를 못 찾았어요 (예매 오픈작만 등록 가능).", False
        if len(movies) > 1:
            opts = "\n".join(f"- {m['movNm']}" for m in movies[:10])
            return f"영화가 여러 개 검색돼요. 더 정확히 써주세요:\n{opts}", False
        watch["mov_no"] = movies[0]["movNo"]
        watch["mov_nm"] = movies[0]["movNm"]
        movie_label = movies[0]["movNm"]
    if dates:
        watch["dates"] = dates
    if times:
        watch["times"] = times

    if config.get("watches") is None:
        config["watches"] = []
    if watch in config["watches"]:
        return "이미 등록돼 있어요.", False
    config["watches"].append(watch)

    # 조건에 맞는 회차를 즉시 조회해서 보여준다 — 시간/날짜 오타로
    # 아무것도 감시하지 않는 상태를 등록 시점에 드러내기 위함
    reply = f"등록했어요 ✅\n{_watch_label(watch)}"
    try:
        records, _ = watcher.fetch_watch(watch)
        if not records:
            reply += (
                "\n⚠️ 지금 이 조건에 맞는 회차가 하나도 없어요."
                "\n날짜/시간이 정확한지 확인해보세요 (시간은 상영시간표의 시작시간과 같아야 해요)."
            )
        else:
            sold = sum(1 for r in records if int(r["frSeatCnt"]) == 0)
            reply += f"\n매칭 회차 {len(records)}개 (현재 매진 {sold}개):"
            for r in records[:5]:
                state = "매진" if int(r["frSeatCnt"]) == 0 else f"잔여 {r['frSeatCnt']}석"
                reply += (
                    f"\n- {watcher.format_date(r['scnYmd'])} "
                    f"{watcher.format_time(r['scnsrtTm'])} {r['scnsNm']} · {state}"
                )
            if len(records) > 5:
                reply += f"\n… 외 {len(records) - 5}개"
            reply += "\n매진 회차에 취소표가 나오면 알려드려요."
    except Exception:
        reply += "\n(회차 확인 조회는 실패했지만 등록은 됐어요)"
    return reply, True


def _open_label(ow: dict) -> str:
    scope = f"CGV {ow['site_nm']}" if ow.get("site_nm") else "전국"
    return f"[오픈 대기] '{ow['query']}' · {scope}"


def _cmd_open(tokens: list[str], config: dict):
    if not tokens:
        return "영화 이름이 필요해요. 예: /open 아바타  또는  /open 용산아이파크몰 아바타", False

    site, words = None, tokens
    if len(tokens) >= 2:
        cands = lookup.find_theaters(tokens[0])
        if len(cands) == 1:
            site, words = cands[0], tokens[1:]
        elif len(cands) > 1:
            opts = "\n".join(f"- {s['siteNm']}" for s in cands[:10])
            return f"극장이 여러 개 검색돼요. 더 정확히 써주세요:\n{opts}", False
    query = " ".join(words)

    ow = {"query": query}
    if site:
        ow["site_no"] = site["siteNo"]
        ow["site_nm"] = site["siteNm"]

    # 이미 오픈됐는지 즉시 확인
    try:
        movies = lookup.find_movies(query)
    except Exception:
        movies = []
    if movies:
        fired, msg = watcher._check_open_watch(ow, movies)
        if fired:
            return "이미 예매가 열려 있어요!\n" + msg.split("\n(")[0] + "\n매진 회차 취소표는 /watch로 감시하세요.", False
        # 전국 기준으론 오픈됐지만 지정 극장엔 아직 → 극장 오픈 대기로 등록 (아래로 진행)

    opens = config.get("opens") or []
    if ow in opens:
        return "이미 등록돼 있어요.", False
    opens.append(ow)
    config["opens"] = opens
    scope = f"CGV {site['siteNm']}에 시간표가 뜨면" if site else "예매가 열리면"
    return f"오픈 알림 등록 ✅\n'{query}' — {scope} 바로 알려드려요.\n(한 번 울리면 자동 해제)", True


def _all_entries(config: dict):
    return [("watch", w) for w in (config.get("watches") or [])] + [
        ("open", o) for o in (config.get("opens") or [])
    ]


def _cmd_list(config: dict):
    entries = _all_entries(config)
    if not entries:
        return "등록된 감시가 없어요. /watch 또는 /open으로 등록하세요.", False
    lines = [
        f"{i}. {_watch_label(item) if kind == 'watch' else _open_label(item)}"
        for i, (kind, item) in enumerate(entries, 1)
    ]
    return "감시 목록:\n" + "\n".join(lines), False


def _cmd_remove(tokens: list[str], config: dict):
    entries = _all_entries(config)
    if not tokens or not tokens[0].isdigit() or not (1 <= int(tokens[0]) <= len(entries)):
        return "해제할 번호를 주세요. 예: /remove 1 (번호는 /list 참고)", False
    kind, item = entries[int(tokens[0]) - 1]
    if kind == "watch":
        config["watches"].remove(item)
        return f"해제했어요 🗑\n{_watch_label(item)}", True
    config["opens"].remove(item)
    return f"해제했어요 🗑\n{_open_label(item)}", True


def _normalize_cmd(text: str) -> str:
    """첫 토큰을 명령어로 정규화. "/watch@봇이름", "watch", "/watch" 모두 "watch"."""
    return text.strip().split()[0].split("@")[0].lstrip("/").lower() if text.strip() else ""


def handle_command(text: str, config: dict, today: datetime.date | None = None):
    """명령 1건 처리 → (응답 문구, config 변경 여부)"""
    today = today or datetime.date.today()
    tokens = text.strip().split()
    cmd = _normalize_cmd(text)
    args = tokens[1:]
    if cmd == "watch":
        return _cmd_watch(args, config, today)
    if cmd == "list":
        return _cmd_list(config)
    if cmd == "remove":
        return _cmd_remove(args, config)
    if cmd == "open":
        return _cmd_open(args, config)
    return HELP, False  # start, help, 그 외 전부


def _send(token: str, chat_id: str, text: str) -> None:
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    ).raise_for_status()


def process_commands(config_path: Path, state_path: Path) -> bool:
    """밀린 텔레그램 명령을 처리하고 config/state를 저장. 변경 여부 반환.

    허용된 chat(TELEGRAM_CHAT_ID)에서 온 메시지만 처리한다.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except ValueError:
            pass

    params = {"timeout": 0, "allowed_updates": '["message"]'}
    if state.get("tg_offset"):
        params["offset"] = state["tg_offset"] + 1
    res = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates", params=params, timeout=15
    )
    res.raise_for_status()
    updates = res.json().get("result", [])
    if not updates:
        return False

    config = configfile.load(config_path)
    changed = False
    for upd in updates:
        state["tg_offset"] = max(state.get("tg_offset", 0), upd["update_id"])
        msg = upd.get("message") or {}
        text = msg.get("text", "").strip()
        if not text:
            continue
        if str(msg.get("chat", {}).get("id")) != str(chat_id):
            continue  # 허용된 chat 외 무시
        # 명령은 /로 시작해야 한다. 일반 문장은 1:1 채팅에서만 도움말 안내 (그룹에선 침묵)
        if not text.startswith("/"):
            if msg.get("chat", {}).get("type") == "private":
                try:
                    _send(token, str(msg["chat"]["id"]), HELP)
                except Exception as e:
                    print(f"[telegram] 응답 발송 실패: {e}")
            continue
        try:
            reply, ch = handle_command(text, config)
        except Exception as e:
            reply, ch = f"처리 중 오류가 났어요: {e}", False
        changed = changed or ch
        try:
            _send(token, str(msg["chat"]["id"]), reply)
        except Exception as e:
            print(f"[telegram] 응답 발송 실패: {e}")

    if changed:
        configfile.save(config_path, config)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    return changed
