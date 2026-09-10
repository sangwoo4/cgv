"""CLI 엔트리포인트: check / loop / status / lookup / test-notify"""

import argparse
import os
import sys
import time
from pathlib import Path

import yaml

from . import lookup, notify, telegram, watcher


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def cmd_status(config: dict) -> int:
    """감시 대상 회차들의 현재 잔여석을 출력 (state 변경 없음)."""
    for watch in config.get("watches") or []:
        records, _ = watcher.fetch_watch(watch)
        if not records:
            print(f"watch {watch}: 해당 회차 없음")
            continue
        for r in records:
            mark = "🔒통제" if r.get("cntlYn") == "Y" else ("❌매진" if int(r["frSeatCnt"]) == 0 else "🟢")
            print(
                f"{mark} {r['siteNm']} {watcher.format_date(r['scnYmd'])} "
                f"{watcher.format_time(r['scnsrtTm'])} {r['movNm']} ({r['scnsNm']}) "
                f"잔여 {r['frSeatCnt']}/{r['stcnt']}석"
            )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="cgv-alarm", description="CGV 취소표 알림")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--state", default="state.json")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="1회 체크 후 종료 (GitHub Actions용)")
    p_loop = sub.add_parser("loop", help="반복 폴링 (Actions/로컬/VPS용)")
    p_loop.add_argument("--interval", type=int, default=120, help="폴링 간격(초)")
    p_loop.add_argument("--rounds", type=int, default=0, help="이 횟수만 돌고 종료 (0=무한)")
    sub.add_parser("status", help="감시 대상 회차의 현재 잔여석 출력")
    p_lookup = sub.add_parser("lookup", help="극장/영화 코드 조회")
    p_lookup.add_argument("kind", choices=["theater", "movie"])
    p_lookup.add_argument("name")
    sub.add_parser("test-notify", help="알림 채널 테스트 발송")

    args = parser.parse_args()
    load_dotenv()

    if args.cmd == "lookup":
        (lookup.print_theaters if args.kind == "theater" else lookup.print_movies)(args.name)
        return
    if args.cmd == "test-notify":
        ok = notify.send_all("✅ CGV 취소표 알람 테스트 메시지입니다.")
        sys.exit(0 if ok else 1)

    if args.cmd == "status":
        sys.exit(cmd_status(load_config(args.config)))

    def one_round():
        # 봇 명령이 config를 바꿀 수 있으니 명령 처리 → 로드 → 체크 순서
        try:
            telegram.process_commands(Path(args.config), Path(args.state))
        except Exception as e:
            print(f"[telegram] 명령 처리 실패: {e}")
        watcher.check_once(Path(args.config), Path(args.state))

    if args.cmd == "check":
        one_round()
        sys.exit(0)
    if args.cmd == "loop":
        n = 0
        while True:
            try:
                one_round()
            except Exception as e:
                print(f"[loop] 체크 실패: {e}")
            n += 1
            if args.rounds and n >= args.rounds:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
