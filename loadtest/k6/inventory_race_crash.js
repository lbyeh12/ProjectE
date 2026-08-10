// loadtest/k6/inventory_race_crash.js
//
// 시나리오 2, 3 공용 실행기.
// adrs/0004-inventory-concurrency-control.md 에서 감수하기로 한 위험
// ("처리 도중 서버가 죽어도 데이터가 안전한가")을 실제로 재현해서 확인한다.
//
// 이 스크립트 자체는 시나리오 1(inventory_race_light.js)과 거의 같다.
// 차이는: (1) VU 수/기간을 늘려서 장애를 겪을 시간 여유를 만들고,
// (2) thresholds를 강제하지 않는다 (연결 끊김/서버 에러가 나는 게
// 오히려 "장애가 의도대로 재현됐다"는 신호이므로 여기서는 실패 처리하지 않음).
//
// 장애 주입: checkout() 코드 안(Kafka 전송 후, commit 전)에 크래시
// 지점을 심어뒀다. 환경변수 대신 컨테이너 안의 파일
// (/tmp/chaos_crash_before_commit) 존재 여부로 켜진다 - 처음에
// 환경변수(CHAOS_CRASH_BEFORE_COMMIT=1) 방식으로 만들었었는데, "매번"
// 크래시가 나서 워커가 재시작된 뒤에도 다음 요청에서 또 죽어 서버가
// 계속 응답 불가 상태로 남는 문제를 실제로 겪었다. 파일은 크래시
// "직전에 스스로 지워지므로" 정확히 한 번만 재현된다.
//
// 실행 방법:
//
//   0. WORKERS=2 이상으로 재시작 (필수). 개발 모드(--reload, WORKERS
//      미지정/1)는 "리로더(PID 1) + 자식 서버" 구조인데, os._exit()로
//      자식이 뚝 끊기는 상황에 대한 복구가 안정적이지 않다 - 실제로
//      컨테이너는 Up인데 서버 프로세스만 죽어 응답이 전혀 없는 상태를
//      겪었다. --workers 모드는 마스터가 워커를 감독하는 진짜
//      멀티프로세스 구조라, 워커가 죽으면 마스터가 즉시 새 워커를
//      띄운다.
//      WORKERS=2 docker compose up -d --force-recreate backend
//
//   1. 크래시 플래그 파일 생성 (0번 재시작 직후, 새로 뜬 컨테이너에)
//      docker exec projecte-backend touch /tmp/chaos_crash_before_commit
//
//   2. 장바구니 정리 + 재고 세팅
//      docker exec -i projecte-postgres psql -U postgres -d projecte \
//        < loadtest/k6/clear_all_carts.sql
//      docker exec -i projecte-postgres psql -U postgres -d projecte \
//        -v product_id="'85123A'" -v stock=5 < loadtest/k6/setup_inventory_test.sql
//
//   3. k6 실행 (재고를 확보하는 첫 번째 구매가 크래시 지점에서 정확히
//      한 번만 죽는다. 그 이후 요청들은 재시작된 프로세스가 정상 처리)
//      k6 run -e PROJECT_ROOT=$(pwd) -e TARGET_PRODUCT_ID=85123A \
//        -e VU_COUNT=50 -e DURATION=30s loadtest/k6/inventory_race_crash.js
//
//   4. (선택, 별도 터미널) backend가 그 순간에 죽고 살아나는지 관찰
//      docker compose logs backend -f
//
// 여러 번 반복 테스트하려면 매번 1번(플래그 파일 생성)부터 다시 한다.
//
// 검증: k6 실행이 끝난 뒤,
// verify_inventory_consistency.sql 의 쿼리로 확인한다.
//   - 시나리오 2 대상 쿼리: DB(재고/주문) 자체의 정합성
//   - 시나리오 3 대상 쿼리: DB와 Kafka(-> Spark -> raw_events/product_stats)
//     사이의 정합성 (이중 쓰기 문제 재현 여부, Spark Streaming이 실행
//     중이어야 함)
import { prepareTestUsers } from "./lib/setup.js";

export { inventoryRace } from "./scenarios/inventory_race.js";

const VU_COUNT = parseInt(__ENV.VU_COUNT || "50", 10);
const DURATION = __ENV.DURATION || "30s";

export const options = {
  scenarios: {
    inventory_race: {
      executor: "constant-vus",
      exec: "inventoryRace",
      vus: VU_COUNT,
      duration: DURATION,
    },
  },
  // 의도적으로 thresholds를 걸지 않는다. 장애 주입 시나리오라
  // purchase_connection_dropped/purchase_server_error가 한 번은 나는 게
  // 오히려 "장애가 재현됐다"는 신호이지, k6 실행의 실패가 아니다.
};

export function setup() {
  return { users: prepareTestUsers(parseInt(__ENV.USER_COUNT || "10", 10)) };
}