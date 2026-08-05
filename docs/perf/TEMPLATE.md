# 성능 측정 기록 템플릿

새 기록을 남길 때 이 파일을 복사해서 `NNN-설명.md` 형식으로 저장한다.
(예: `001-baseline.md`, `002-after-random-account-selection.md`)

## 언제

- 날짜:
- 관련 ADR:
- 이 측정 직전에 무엇을 바꿨나 (없으면 "기준선(baseline)"이라고 표기):

## 실행 조건

- 스크립트: (smoke / load / stress)
- 목표 VU:
- 지속 시간:
- 실행 환경: (로컬 Docker Compose / 기타. Spark 동시 실행 여부도 명시)

## 결과 요약

| 지표 | 값 |
|---|---|
| http_req_duration p95 | |
| http_req_duration p99 | |
| http_req_failed (에러율) | |
| iterations (완료 수) | |
| vus_max | |

## 관찰된 병목

무엇이 먼저 무너졌는가? (예: "VU 300 근처부터 /purchase 응답시간이 급증,
동시에 DB 커넥션 풀 고갈 로그 확인")

이게 "애플리케이션 자체의 병목"인지 "테스트 환경(로컬 머신)의 리소스
한계"인지 구분해서 적는다 (`docker stats`로 특정 컨테이너만 튀는지,
전체가 골고루 포화됐는지 확인).

## 다음 액션

이 결과를 바탕으로 어떤 항목을 다음에 적용할지 (UPGRADE_PLAN.md 항목 참조).

## Related

- Related ADRs:
- 이전 기록:
