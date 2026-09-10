"""CLI 엔트리포인트: check / loop / status / lookup / test-notify"""

import argparse
import os
import sys
import time
from pathlib import Path

import yaml

from . import lookup, notify, watcher


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
    p_loop = sub.add_parser("loop", help="상시 폴링 (로컬/VPS용)")
    p_loop.add_argument("--interval", type=int, default=120, help="폴링 간격(초)")
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

    config = load_config(args.config)
    if args.cmd == "status":
        sys.exit(cmd_status(config))
    if args.cmd == "check":
        sys.exit(watcher.check_once(config, Path(args.state)))
    if args.cmd == "loop":
        while True:
            try:
                watcher.check_once(config, Path(args.state))
            except Exception as e:
                print(f"[loop] 체크 실패: {e}")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
