# CGV 취소표 알람

매진된 CGV 상영회차에 취소표(빈 좌석)가 생기면 텔레그램/디스코드로 알림을 보낸다.
GitHub Actions cron(5분 간격)으로 무료로 돌아가며 서버가 필요 없다.

## 동작 원리

CGV 비공식 API(`cgv.co.kr/api/v1/booking/*`)에서 회차별 잔여석(`frSeatCnt`)을
조회하고, `0 → 양수` 전환을 감지하면 알림을 보낸다. 로그인·쿠키 불필요.
(Cloudflare가 TLS 지문을 검사해 데이터센터 IP에서 403을 주므로, curl_cffi의
브라우저 지문 모방으로 우회한다 — GitHub Actions 러너에서 검증됨)

- 매진 판정: `frSeatCnt == 0 && cntlYn == 'N'` (`cntlYn == 'Y'`는 판매통제/미오픈)
- 알림 후 재매진되기 전까지는 같은 회차로 다시 알리지 않음
- 상태는 `state.json`으로 유지 (Actions에서는 cache로 전달)

## 설정

### 1. 알림 채널

- **텔레그램**: [@BotFather](https://t.me/BotFather)에서 `/newbot`으로 봇 생성 → 토큰 확보.
  받을 사람이 봇에게 아무 메시지나 보낸 뒤
  `https://api.telegram.org/bot<토큰>/getUpdates` 를 열면 `chat.id`가 보인다.
  (여러 명이 받으려면 그룹을 만들어 봇을 초대하고 그룹의 chat id를 쓰면 된다)
- **디스코드**: 채널 설정 → 연동 → 웹후크 만들기 → URL 복사.

GitHub 저장소 → Settings → Secrets and variables → Actions 에 등록:

| Secret | 값 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather가 준 토큰 |
| `TELEGRAM_CHAT_ID` | 받는 사람/그룹의 chat id |
| `DISCORD_WEBHOOK_URL` | 웹후크 URL |

설정 안 한 채널은 자동으로 건너뛴다.

### 2. 감시 대상

**방법 A — 텔레그램 봇 명령 (받는 사람이 직접):**

봇에게 메시지를 보내면 된다. 처리는 다음 cron 주기(최대 5~10분)에 되고 확인 답장이 온다.

```
/watch 용산 오디세이 0912 18:00   ← 감시 등록
/watch 용산 오디세이              ← 날짜/시간 생략 = 오픈된 전 회차
/list                             ← 감시 목록
/remove 1                         ← 해제
/help                             ← 도움말
```

날짜는 `0912`(올해, 지난 날짜면 내년) 또는 `20260912`, 시간은 `18:00` 형식.
등록된 감시는 봇이 `config.yaml`에 자동 커밋한다.
`TELEGRAM_CHAT_ID`로 지정된 채팅의 명령만 받는다.

**방법 B — config.yaml 직접 수정:**

극장/영화 코드를 조회해서 `config.yaml`에 넣고 커밋:

```bash
uv run cgv-alarm lookup theater 용산    # → 0013  CGV 용산아이파크몰
uv run cgv-alarm lookup movie 오디세이   # → 30001323  오디세이
```

```yaml
watches:
  - site_no: "0013"
    mov_no: "30001323"
    dates: ["20260912"]   # 생략 시 예매 오픈된 모든 날짜
    times: ["1800"]       # 생략 시 전 회차
```

## 로컬 사용법

```bash
uv sync
cp .env.example .env       # 토큰 채우기 (로컬 테스트용)
uv run cgv-alarm test-notify          # 채널 테스트
uv run cgv-alarm status               # 감시 대상 현재 잔여석 조회
uv run cgv-alarm check                # 1회 체크 (Actions가 도는 방식)
uv run cgv-alarm loop --interval 120  # 상시 폴링 (VPS/로컬용)
uv run pytest                         # 전환 감지 로직 테스트
```

## 한계와 주의

- GitHub Actions cron은 최소 5분 간격이고 혼잡 시 10~20분 지연될 수 있다.
  초경쟁 회차라 더 빠른 감지가 필요하면 VPS에서 `loop` 명령으로 돌리면 된다.
- 비공식 API를 조회 전용·저빈도로만 사용한다. 좌석 자동 선점 기능은 만들지 않는다.
- 회차 단위 예매 딥링크는 CGV 구조상 없어서, 알림에는 극장 페이지 링크가 담긴다.
