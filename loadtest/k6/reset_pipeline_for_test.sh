#!/bin/bash
# loadtest/k6/reset_pipeline_for_test.sh
#
# 재고 경쟁 시나리오(특히 시나리오 3, DB-Kafka 정합성 검증)를 실행하기
# 전에, 이전 테스트/사용의 흔적을 전부 지운다. 지우지 않으면
# raw_events/product_stats 에 과거 누적치가 남아있어 "이번 테스트로
# 발생한 이벤트 수"를 정확히 셀 수 없다.
#
# 지우는 대상:
#   1. cart_items       - 모든 사용자 장바구니
#   2. raw_events       - purchase 이벤트 누적 기록 (use_kafka=false 폴백 경로)
#   3. product_stats, traffic_stats - Spark가 overwrite로 다시 쓰는 집계 테이블
#   4. Kafka 토픽(user-events)의 메시지 - 토픽을 삭제 후 재생성
#   5. Spark 체크포인트 - 토픽을 새로 만들면 offset이 안 맞아 기존
#      체크포인트로는 읽을 수 없으므로 같이 지운다
#
# 주의: 이 스크립트는 "테스트/개발 환경 초기화용"이다. 실제 운영 중인
# 데이터가 있는 환경에서는 절대 실행하지 않는다.
#
# 사용법:
#   bash loadtest/k6/reset_pipeline_for_test.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "[1/5] 장바구니 정리..."
docker exec -i projecte-postgres psql -U postgres -d projecte \
  < "$SCRIPT_DIR/clear_all_carts.sql"

echo "[2/5] raw_events / product_stats / traffic_stats 초기화..."
docker exec -i projecte-postgres psql -U postgres -d projecte <<'SQL'
TRUNCATE TABLE raw_events;
TRUNCATE TABLE product_stats;
TRUNCATE TABLE traffic_stats;
SQL

echo "[3/5] Kafka 토픽(user-events) 삭제 후 재생성..."
docker exec projecte-kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --delete --topic user-events || \
  echo "  (토픽이 없었거나 이미 삭제됨 - 계속 진행)"

# Kafka의 토픽 삭제는 비동기라 삭제 명령이 끝났다고 즉시 목록에서
# 사라지는 게 보장되지 않는다. 삭제 진행 중에 재생성하면 실패/누락될
# 수 있으므로, 토픽이 실제로 목록에서 사라질 때까지 최대 15초간 반복 확인한다.
echo "  토픽이 실제로 삭제될 때까지 대기 중..."
for i in $(seq 1 15); do
  if ! docker exec projecte-kafka /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 --list | grep -q "^user-events$"; then
    echo "  삭제 확인됨 (${i}초 소요)"
    break
  fi
  sleep 1
done

docker exec projecte-kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --create --topic user-events \
  --partitions 3 --replication-factor 1

# 생성도 즉시 목록에 반영 안 될 수 있어, 확실히 생성됐는지 최종 확인.
echo "  토픽 생성 확인 중..."
for i in $(seq 1 10); do
  if docker exec projecte-kafka /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 --list | grep -q "^user-events$"; then
    echo "  생성 확인됨 (${i}초 소요)"
    break
  fi
  if [ "$i" -eq 10 ]; then
    echo "  경고: 10초 안에 토픽 생성이 확인되지 않았습니다. 수동으로 확인하세요:"
    echo "    docker exec projecte-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list"
  fi
  sleep 1
done

echo "[4/5] Spark 체크포인트 삭제..."
if [ -d "$PROJECT_ROOT/spark/.checkpoints" ]; then
  rm -rf "$PROJECT_ROOT/spark/.checkpoints"
  echo "  삭제 완료: $PROJECT_ROOT/spark/.checkpoints"
else
  echo "  체크포인트 폴더 없음 (이미 초기화된 상태)"
fi

echo "[5/5] 완료."
echo ""
echo "다음 순서로 진행하세요:"
echo "  1. Spark Streaming 재시작 (기존 프로세스가 있다면 먼저 Ctrl+C):"
echo "     source venv-spark/bin/activate && bash spark/run_streaming.sh"
echo "  2. 재고 세팅 후 k6 실행"