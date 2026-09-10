#!/bin/bash
# GitHub Actions의 watch 실행 로그를 터미널에서 따라간다.
# run이 완료될 때마다 그 실행의 로그를 출력. Ctrl-C로 종료.
set -euo pipefail
REPO=sangwoo4/cgv
LAST=""
echo "▶ $REPO watch 로그 대기 중... (run 완료마다 출력, Ctrl-C 종료)"
while true; do
  RID=$(gh run list --repo $REPO --workflow watch --limit 1 \
        --json databaseId,status --jq '.[] | select(.status=="completed") | .databaseId' 2>/dev/null || true)
  if [ -n "$RID" ] && [ "$RID" != "$LAST" ]; then
    LAST=$RID
    CONC=$(gh run list --repo $REPO --workflow watch --limit 1 --json conclusion --jq '.[0].conclusion')
    echo ""
    echo "── run $RID ($CONC) $(date '+%H:%M:%S') ──"
    gh run view "$RID" --repo $REPO --log 2>/dev/null \
      | grep -oE '\[(watcher|telegram|notify|loop)\].*' || echo "(로그 라인 없음)"
  fi
  sleep 30
done
