"""CGV 비공식 API 클라이언트.

전 엔드포인트가 인증 없는 GET·JSON. Cloudflare는 HTTP/1.1 + 브라우저 UA면
통과하므로 requests(기본 HTTP/1.1)로 충분하다. HTTP/2로 붙으면 403이 난다.
"""

import time

import requests

BASE = "https://cgv.co.kr/api/v1"
CO_CD = "A420"  # CJ CGV 한국 법인코드 (고정)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Referer": "https://cgv.co.kr/cnm/movieBook/cinema",
    "Accept": "application/json",
}


class ApiError(Exception):
    pass


def _get(path: str, params: dict, retries: int = 2):
    params = {"coCd": CO_CD, **params}
    last_err = None
    for attempt in range(retries + 1):
        try:
            res = requests.get(f"{BASE}{path}", params=params, headers=HEADERS, timeout=15)
            if res.status_code != 200:
                raise ApiError(f"HTTP {res.status_code} {path}")
            body = res.json()
            if body.get("statusCode") != 0:
                raise ApiError(
                    f"statusCode={body.get('statusCode')} ({body.get('statusMessage')}) {path}"
                )
            return body["data"]
        except (requests.RequestException, ValueError, KeyError, ApiError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise ApiError(str(last_err))


def _schedule(path: str, params: dict, site_no: str, ymd: str) -> list[dict]:
    data = _get(path, params)
    if not isinstance(data, list):
        raise ApiError(f"예상 밖 응답 형태 (list 아님) {path}")
    # 응답 레코드에는 요청 컨텍스트(극장/날짜)가 빠져 있을 수 있어 붙여 준다
    for rec in data:
        rec.setdefault("siteNo", site_no)
        rec.setdefault("scnYmd", ymd)
    return data


def schedule_by_movie(site_no: str, ymd: str, mov_no: str) -> list[dict]:
    """특정 극장×날짜×영화의 회차별 시간표 + 잔여석(frSeatCnt)."""
    return _schedule(
        "/booking/searchSchByMov",
        {"siteNo": site_no, "scnYmd": ymd, "movNo": mov_no, "rtctlScopCd": "01"},
        site_no,
        ymd,
    )


def schedule_all(site_no: str, ymd: str) -> list[dict]:
    """특정 극장×날짜의 전체 회차 시간표 + 잔여석."""
    return _schedule(
        "/booking/searchMovScnInfo",
        {"siteNo": site_no, "scnYmd": ymd, "rtctlScopCd": "01"},
        site_no,
        ymd,
    )


def open_dates(site_no: str) -> list[str]:
    """해당 극장에서 예매 오픈된 날짜(YYYYMMDD) 목록."""
    data = _get("/booking/searchSiteScnscYmdListBySite", {"siteNo": site_no})
    return [d["scnYmd"] for d in data]


def all_sites() -> list[dict]:
    """전 지점 목록. [{regnGrpCd, siteNo, siteNm}, ...]"""
    data = _get("/content/site/searchAllRegionAndSite", {})
    return data["siteInfo"]


def movies_on_sale() -> list[dict]:
    """예매 중인 영화 목록. [{movNo, movNm, atktRate, ...}, ...]"""
    return _get("/booking/searchAtktTopPostrList", {"movNm": "", "div": "", "attrCd": ""})
