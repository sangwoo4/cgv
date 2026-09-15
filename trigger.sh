#!/bin/bash
# GitHub cron이 신뢰 불가라, 로컬에서 5분마다 cgv-watch 워크플로를 원격 트리거한다.
# launchd(com.sangwoo.cgv-trigger)가 이 스크립트를 실행한다.
export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH
LOG=/tmp/cgv-trigger.log
TOKEN=$(gh auth token --user sangwoo4 2>/dev/null)
if [ -z "$TOKEN" ]; then echo "$(date '+%F %T') token-fail" >> "$LOG"; exit 0; fi
if GH_TOKEN=$TOKEN gh api -X POST \
  repos/sangwoo4/cgv/actions/workflows/cgv-watch.yml/dispatches \
  -f ref=main >/dev/null 2>&1; then
  echo "$(date '+%F %T') dispatched" >> "$LOG"
else
  echo "$(date '+%F %T') dispatch-fail" >> "$LOG"
fi
