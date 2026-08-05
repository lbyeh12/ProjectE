// loadtest/k6/debug_open.js
//
// users.csv 를 못 읽는 문제를 진단하기 위한 최소 스크립트.
// 이것만 단독으로 실행해서 정확히 어떤 에러가 나는지 확인한다.
//
// 실행: k6 run -e PROJECT_ROOT=$(pwd) loadtest/k6/debug_open.js
const PROJECT_ROOT = __ENV.PROJECT_ROOT || ".";
const path = `${PROJECT_ROOT}/data/dataset/users.csv`;

console.log("시도할 경로:", path);

try {
  const content = open(path);
  console.log("성공! 파일 크기(문자 수):", content.length);
  console.log("첫 줄:", content.split("\n")[0]);
} catch (e) {
  console.log("실패! 에러 메시지:", e.message);
}

export default function () {}
