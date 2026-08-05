// loadtest/k6/lib/config.js
//
// 모든 시나리오/엔트리 스크립트가 공유하는 설정.
// BASE_URL 은 환경변수로 덮어쓸 수 있다 (로컬/도커/스테이징 등 환경별로).
//
//   k6 run -e BASE_URL=http://localhost:8000 loadtest/k6/load.js

export const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

// 부하 테스트 전용 계정에 공통으로 쓰는 비밀번호.
// (data/dataset/users.csv 의 실제 user_id 에 이 비밀번호를 설정해서 로그인 흐름을 검증한다.
//  운영 계정이 아니라 로컬/CI 테스트 목적의 값이라 코드에 그대로 둔다.)
export const TEST_PASSWORD = "loadtest1234";
