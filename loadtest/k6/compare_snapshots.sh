#!/bin/bash
# loadtest/k6/compare_snapshots.sh
#
# snapshot_inventory_state.sh 로 찍은 두 스냅샷(before/after)의 차이를
# 계산해서, "이번 테스트가 만든 변화"만 정확히 추출한다.
#
# 판정 기준:
#   - DB 기준 구매 수 (stock 감소분) 와
#   - Kafka 기준 구매 수 (raw_events, product_stats 증가분)
#   이 서로 일치해야 "이중 쓰기 없이 정합성이 지켜졌다"고 본다.
#
# 사용법:
#   bash loadtest/k6/compare_snapshots.sh before after
set -e

BEFORE_LABEL="${1:?사용법: compare_snapshots.sh <before라벨> <after라벨>}"
AFTER_LABEL="${2:?사용법: compare_snapshots.sh <before라벨> <after라벨>}"

SNAPSHOT_DIR="/tmp/inventory_snapshots"
BEFORE_FILE="$SNAPSHOT_DIR/${BEFORE_LABEL}.env"
AFTER_FILE="$SNAPSHOT_DIR/${AFTER_LABEL}.env"

if [ ! -f "$BEFORE_FILE" ]; then
  echo "에러: ${BEFORE_FILE} 가 없습니다. snapshot_inventory_state.sh 를 먼저 실행하세요."
  exit 1
fi
if [ ! -f "$AFTER_FILE" ]; then
  echo "에러: ${AFTER_FILE} 가 없습니다. snapshot_inventory_state.sh 를 먼저 실행하세요."
  exit 1
fi

# .env 파일을 각각 다른 접두어(BEFORE_/AFTER_)로 불러온다.
while IFS='=' read -r key value; do
  [ -z "$key" ] && continue
  export "BEFORE_${key}=${value}"
done < "$BEFORE_FILE"

while IFS='=' read -r key value; do
  [ -z "$key" ] && continue
  export "AFTER_${key}=${value}"
done < "$AFTER_FILE"

if [ "$BEFORE_PRODUCT_ID" != "$AFTER_PRODUCT_ID" ]; then
  echo "경고: before(${BEFORE_PRODUCT_ID})와 after(${AFTER_PRODUCT_ID})의 product_id가 다릅니다."
fi

STOCK_DECREASED=$((BEFORE_STOCK - AFTER_STOCK))
RAW_EVENTS_INCREASED=$((AFTER_RAW_EVENTS_COUNT - BEFORE_RAW_EVENTS_COUNT))
PRODUCT_STATS_INCREASED=$((AFTER_PRODUCT_STATS_COUNT - BEFORE_PRODUCT_STATS_COUNT))

echo "=================================================="
echo "product_id: ${AFTER_PRODUCT_ID}"
echo "--------------------------------------------------"
echo "DB 기준 구매 수 (재고 감소분)      : ${STOCK_DECREASED}"
echo "raw_events 증가분 (Kafka 경로)     : ${RAW_EVENTS_INCREASED}"
echo "product_stats 증가분 (Spark 집계)  : ${PRODUCT_STATS_INCREASED}"
echo "--------------------------------------------------"

MISMATCH_RAW=$((STOCK_DECREASED - RAW_EVENTS_INCREASED))
MISMATCH_STATS=$((STOCK_DECREASED - PRODUCT_STATS_INCREASED))

echo "mismatch (DB vs raw_events)        : ${MISMATCH_RAW}"
echo "mismatch (DB vs product_stats)      : ${MISMATCH_STATS}"
echo "=================================================="

if [ "$MISMATCH_RAW" -eq 0 ] && [ "$MISMATCH_STATS" -eq 0 ]; then
  echo "결과: 정합성 유지됨 (이중 쓰기 불일치 없음)"
  exit 0
else
  echo "결과: 불일치 발견 - 이중 쓰기 문제가 재현된 것으로 보임"
  exit 1
fi
