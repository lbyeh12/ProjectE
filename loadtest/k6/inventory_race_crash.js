// loadtest/k6/inventory_race_crash.js
//
// 시나리오 2, 3 공용 실행기. adrs/0004-inventory-concurrency-control.md
// 에서 감수하기로 한 위험("처리 도중 서버가 죽어도 데이터가 안전한가")을
// 재현해서 확인한다. 장애 주입은 checkout() 코드 안(Kafka 전송 후,
// commit 전)에 심어둔 크래시 지점을 컨테이너 안의 파일
// (/tmp/chaos_crash_before_commit) 존재 여부로 켠다.
//
// inventory_race_light.js(시나리오 1)와 거의 같되, VU 수/기간을 늘리고
// thresholds를 강제하지 않는다(연결 끊김/서버 에러가 나는 게 오히려
// "장애가 재현됐다"는 신호이므로).
//
// 실행 방법, 사전 준비, 검증 절차는 loadtest/k6/README.md 참고.
// 관측 결과는 docs/perf/006-inventory-race.md 참고.
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
  // 의도적으로 thresholds를 걸지 않는다: 장애 주입 시나리오라
  // 연결 끊김/서버 에러가 나는 게 "장애가 재현됐다"는 신호이지 실패가 아니다.
};

export function setup() {
  return { users: prepareTestUsers(parseInt(__ENV.USER_COUNT || "10", 10)) };
}