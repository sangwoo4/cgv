"""텔레그램 봇 명령 처리: /watch /list /remove /help

봇이 상주하지 않는 구조(Actions cron)라 매 실행마다 getUpdates로 밀린
명령을 모아 처리한다. 응답은 다음 cron 주기(최대 5~10분)에 도착한다.
명령으로 바뀐 감시 대상은 config.yaml에 저장되고 워크플로가 커밋한다.
"""

import datetime
import json
import os
from pathlib import Path

import requests
import yaml

from . import lookup

HELP = """CGV 취소표 알람 봇 명령:

/watch 극장 [영화] [날짜] [시간] — 감시 등록
  예: /watch 용산 오디세이 0912 18:00
  날짜는 0912 또는 20260912, 시간은 18:00 형식 (여러 개 가능)
  영화 생략 시 극장 전체, 날짜 생략 시 예매 오픈된 전 날짜
/list — 감시 목록
/remove 번호 — 감시 해제 (/list에 나온 번호)
/help — 이 도움말

명령 처리는 최대 5~10분 걸릴 수 있어요.
매진 회차에 취소표가 나오면 바로 알려드립니다."""

CONFIG_HEADER = (
    "# 감시 대상 설정 — 텔레그램 봇 명령(/watch)으로도 관리됩니다.\n"
    "# 필드 설명과 코드 조회 방법은 README 참고.\n"
)


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
    return f"등록했어요 ✅\n{_watch_label(watch)}\n({movie_label} 매진 회차에 취소표가 나오면 알림)", True


def _cmd_list(config: dict):
    watches = config.get("watches") or []
    if not watches:
        return "등록된 감시가 없어요. /watch로 등록하세요.", False
    lines = [f"{i}. {_watch_label(w)}" for i, w in enumerate(watches, 1)]
    return "감시 목록:\n" + "\n".join(lines), False


def _cmd_remove(tokens: list[str], config: dict):
    watches = config.get("watches") or []
    if not tokens or not tokens[0].isdigit() or not (1 <= int(tokens[0]) <= len(watches)):
        return "해제할 번호를 주세요. 예: /remove 1 (번호는 /list 참고)", False
    removed = watches.pop(int(tokens[0]) - 1)
    return f"해제했어요 🗑\n{_watch_label(removed)}", True


def handle_command(text: str, config: dict, today: datetime.date | None = None):
    """명령 1건 처리 → (응답 문구, config 변경 여부)"""
    today = today or datetime.date.today()
    tokens = text.strip().split()
    cmd = tokens[0].split("@")[0].lower()  # "/watch@봇이름" 형태 지원
    args = tokens[1:]
    if cmd == "/watch":
        return _cmd_watch(args, config, today)
    if cmd == "/list":
        return _cmd_list(config)
    if cmd == "/remove":
        return _cmd_remove(args, config)
    return HELP, False  # /start, /help, 그 외 전부


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

    config = yaml.safe_load(config_path.read_text()) or {}
    changed = False
    for upd in updates:
        state["tg_offset"] = max(state.get("tg_offset", 0), upd["update_id"])
        msg = upd.get("message") or {}
        text = msg.get("text", "")
        if not text.startswith("/"):
            continue
        if str(msg.get("chat", {}).get("id")) != str(chat_id):
            continue  # 허용된 chat 외 무시
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
        config_path.write_text(
            CONFIG_HEADER + yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
        )
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    return changed
