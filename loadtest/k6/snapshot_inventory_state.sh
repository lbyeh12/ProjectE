#!/bin/bash
# loadtest/k6/snapshot_inventory_state.sh
#
# 재고/이벤트 관련 상태를 특정 시점에 찍어서 파일로 저장한다.
# 테스트 전(before)과 후(after) 두 번 찍어서 compare_snapshots.sh 로
# 차이를 계산하면, 과거에 쌓인 데이터가 얼마나 있든 상관없이 "이번
# 테스트가 만든 변화"만 정확히 격리해서 볼 수 있다.
#
# 사용법:
#   bash loadtest/k6/snapshot_inventory_state.sh before 85123A
#   (... 테스트 실행 ...)
#   bash loadtest/k6/snapshot_inventory_state.sh after 85123A
set -e

LABEL="${1:?사용법: snapshot_inventory_state.sh <라벨(예: before/after)> <product_id>}"
PRODUCT_ID="${2:?사용법: snapshot_inventory_state.sh <라벨> <product_id>}"

OUT_DIR="/tmp/inventory_snapshots"
mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/${LABEL}.env"

# product_stats 테이블이 아직 없을 수 있다 (Spark를 한 번도 안 띄웠거나
# 이번이 시나리오 2까지만이라 3번을 안 돌린 경우) - 있으면 값을, 없으면
# 0을 쓴다. psql 에러로 스크립트가 죽지 않도록 || true 로 처리.
STOCK=$(docker exec -i projecte-postgres psql -U postgres -d projecte -t -A \
  -c "SELECT stock FROM products WHERE product_id = '${PRODUCT_ID}';")

RAW_EVENTS_COUNT=$(docker exec -i projecte-postgres psql -U postgres -d projecte -t -A \
  -c "SELECT count(*) FROM raw_events WHERE event_type='purchase' AND product_id='${PRODUCT_ID}';")

PRODUCT_STATS_COUNT=$(docker exec -i projecte-postgres psql -U postgres -d projecte -t -A \
  -c "SELECT COALESCE(purchase_count, 0) FROM product_stats WHERE product_id='${PRODUCT_ID}';" \
  2>/dev/null || echo "0")
if [ -z "$PRODUCT_STATS_COUNT" ]; then
  PRODUCT_STATS_COUNT=0
fi

cat > "$OUT_FILE" <<EOF
PRODUCT_ID=${PRODUCT_ID}
STOCK=${STOCK}
RAW_EVENTS_COUNT=${RAW_EVENTS_COUNT}
PRODUCT_STATS_COUNT=${PRODUCT_STATS_COUNT}
TAKEN_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

echo "[snapshot:${LABEL}] product_id=${PRODUCT_ID} stock=${STOCK} raw_events=${RAW_EVENTS_COUNT} product_stats=${PRODUCT_STATS_COUNT}"
echo "저장됨: ${OUT_FILE}"
