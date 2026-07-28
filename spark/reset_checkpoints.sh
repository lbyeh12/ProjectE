#!/bin/bash
# ============================================================
# Spark 체크포인트 초기화 스크립트
#
# 언제 실행해야 하나:
#   - docker compose down -v 로 Kafka 볼륨을 지웠을 때
#   - Kafka 토픽을 수동으로 삭제/재생성했을 때
#   - Spark 실행 시 아래와 같은 에러가 날 때:
#     "Some data may have been lost because they are not available
#      in Kafka any more" / "Partitions ... have been deleted"
#
# Kafka 데이터를 정상적으로 계속 쓰는 경우(껐다 켜기만 한 경우)에는
# 이 스크립트를 실행할 필요가 없다. 체크포인트를 지우면 Spark가
# 지금까지 처리한 위치를 잊고 처음부터(또는 latest 설정에 따라) 다시 읽는다.
#
# 사용:
#   bash spark/reset_checkpoints.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-$SCRIPT_DIR/.checkpoints}"

if [ -d "$CHECKPOINT_DIR" ]; then
  echo "체크포인트 삭제: $CHECKPOINT_DIR"
  rm -rf "$CHECKPOINT_DIR"
  echo "완료. 다음 Spark 실행 시 새로 시작합니다."
else
  echo "체크포인트 폴더가 없습니다 (이미 초기화된 상태): $CHECKPOINT_DIR"
fi
