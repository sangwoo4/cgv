"""극장/영화 이름 → 코드 조회 (config.yaml 채우기용)."""

from . import api


def find_theaters(name: str) -> list[dict]:
    return [s for s in api.all_sites() if name in s["siteNm"]]


def find_movies(name: str) -> list[dict]:
    return [m for m in api.movies_on_sale() if name in m["movNm"]]


def print_theaters(name: str) -> None:
    rows = find_theaters(name)
    if not rows:
        print(f"'{name}' 극장을 찾지 못했습니다")
        return
    for s in rows:
        print(f"{s['siteNo']}  CGV {s['siteNm']}")


def print_movies(name: str) -> None:
    rows = find_movies(name)
    if not rows:
        print(f"'{name}' 영화를 찾지 못했습니다 (예매 오픈작만 검색됩니다)")
        return
    for m in rows:
        rate = f"  예매율 {m['atktRate']}%" if m.get("atktRate") else ""
        print(f"{m['movNo']}  {m['movNm']}{rate}")
