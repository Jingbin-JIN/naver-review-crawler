#!/bin/bash
# 맥에서 처음 한 번: 가상환경(.venv) → 패키지 → 브라우저(Chromium) → 테스트
set -e
cd "$(dirname "$0")"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
  echo "Python 3.9 이상이 필요합니다."
  echo "- '명령어 라인 개발자 도구' 설치 창이 떴다면 '설치'를 눌러 끝낸 뒤 다시 실행하세요."
  echo "- 창이 안 떴다면 https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요."
  exit 1
fi

echo "[1/4] 가상환경 준비 (.venv)"
[ -x .venv/bin/python ] || python3 -m venv .venv
echo "[2/4] 패키지 설치"
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
echo "[3/4] 브라우저(Chromium) 설치 - 처음에는 1~2분 걸립니다"
.venv/bin/python -m playwright install chromium
echo "[4/4] 테스트"
.venv/bin/python -m unittest
echo
echo "준비 완료. 팀 시트를 xlsx로 받은 뒤 이렇게 실행하세요:"
echo '  .venv/bin/python crawl.py run --input "받은 파일.xlsx" --sheet 팀원A'
