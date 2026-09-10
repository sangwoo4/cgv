"""config.yaml 로드/저장 — 봇 명령과 watcher가 공유."""

from pathlib import Path

import yaml

HEADER = (
    "# 감시 대상 설정 — 텔레그램 봇 명령(/watch, /open)으로도 관리됩니다.\n"
    "# 필드 설명과 코드 조회 방법은 README 참고.\n"
)


def load(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def save(path: Path, config: dict) -> None:
    Path(path).write_text(HEADER + yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
