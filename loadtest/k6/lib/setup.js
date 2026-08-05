// loadtest/k6/lib/setup.js
//
// 부하 테스트 "시작 시 한 번만" 실행되는 준비 로직 (k6의 setup() 단계에서 호출됨).
// VU들이 몰려들기 전에, 로그인 흐름 테스트에 쓸 계정을 실제 데이터셋에서 준비해둔다.
//
// 우리 회원가입(POST /auth/signup)은 "데이터셋에 이미 존재하는 user_id"에만
// 비밀번호를 설정할 수 있어서, users.csv 를 직접 읽어 몇 명을 뽑아 미리
// signup 을 호출해둔다. (이미 비밀번호가 설정돼 있으면 400이 오는데,
// 그 경우도 "로그인은 가능한 계정"으로 취급한다.)
import http from "k6/http";
import { BASE_URL, TEST_PASSWORD } from "./config.js";

const PROJECT_ROOT = __ENV.PROJECT_ROOT || ".";
const USERS_CSV_PATH = `${PROJECT_ROOT}/data/dataset/users.csv`;

// k6 의 open() 은 반드시 "init 컨텍스트"(스크립트가 로드되는 즉시 실행되는
// 최상위 코드)에서만 호출할 수 있다. setup()이나 다른 함수 안에서 나중에
// 호출하면 조용히 실패한다 (에러 메시지 없이 그냥 못 읽은 것처럼 동작함 —
// 실제로 이 문제로 한참 헤맸다). 그래서 파일 "읽기"는 여기 최상위에서
// 모듈이 로드되는 즉시 끝내두고, 실제 회원가입 HTTP 호출만 아래
// prepareTestUsers() 안에서(= setup() 단계에서) 수행한다.
let USERS_CSV_TEXT = null;
try {
  USERS_CSV_TEXT = open(USERS_CSV_PATH);
} catch (e) {
  console.warn(
    `[setup] users.csv 를 찾을 수 없습니다 (${USERS_CSV_PATH}). ` +
      `purchase_flow 시나리오는 건너뜁니다. 먼저 data/preprocess.py 를 실행하세요.`
  );
}

function parseUserIdsFromCsv(csvText) {
  const lines = csvText.trim().split("\n");
  const header = lines[0].split(",");
  const userIdCol = header.indexOf("user_id");
  if (userIdCol === -1) {
    throw new Error(`users.csv 에 user_id 컬럼이 없습니다. header=${header}`);
  }
  return lines.slice(1).map((line) => line.split(",")[userIdCol]).filter(Boolean);
}

/** Fisher-Yates 셔플로 배열에서 n개를 무작위로 뽑는다. */
function sample(arr, n) {
  const copy = arr.slice();
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, n);
}

/**
 * users.csv 에서 n명을 뽑아 회원가입시키고, 로그인 가능한 계정 목록을 반환한다.
 * k6 의 setup() 안에서 호출한다. (파일 읽기는 이미 위쪽 init 단계에서 끝났고,
 * 여기서는 그 결과(USERS_CSV_TEXT)를 파싱하고 HTTP 요청만 보낸다.)
 */
export function prepareTestUsers(n) {
  if (!USERS_CSV_TEXT) {
    return [];
  }

  const allIds = parseUserIdsFromCsv(USERS_CSV_TEXT);
  const sampledIds = sample(allIds, Math.min(n, allIds.length));

  const users = [];
  for (const userId of sampledIds) {
    const res = http.post(
      `${BASE_URL}/auth/signup`,
      JSON.stringify({ user_id: Number(userId), password: TEST_PASSWORD }),
      { headers: { "Content-Type": "application/json" } }
    );
    // 200/201(신규 성공) 또는 400(이미 비밀번호 설정된 계정) 둘 다 로그인 가능하다고 간주.
    if ([200, 201, 400].includes(res.status)) {
      users.push({ user_id: Number(userId), password: TEST_PASSWORD });
    }
  }

  console.log(`[setup] 로그인 테스트 계정 ${users.length}개 준비 완료`);
  return users;
}