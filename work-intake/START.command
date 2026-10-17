#!/bin/sh
# Local Mac launcher: extract the whole ZIP before opening this file.
# For an existing AI conversation, attach the complete START.md instead and
# explicitly ask to use the assistant. Uploading this shell file alone is not setup.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3 is needed / 需要 Python 3 / Python 3 が必要です'
  read -r _work_intake_wait
  exit 1
fi
if [ -f .launcher/launch.py ]; then
  task_launcher=.launcher/launch.py
elif [ -f launch.py ]; then
  task_launcher=launch.py
else
  echo 'Package incomplete: extract the whole ZIP / 请完整解压 / ZIP全体を展開 / ZIP 전체를 풀어 주세요'
  read -r _work_intake_wait
  exit 1
fi
python3 -B "$task_launcher" "$@"
task_result=$?
if [ "$task_result" -ne 0 ]; then read -r _work_intake_wait; fi
exit "$task_result"
