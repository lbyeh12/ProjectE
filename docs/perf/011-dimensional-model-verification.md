# 011: 차원 모델 ETL 검증

## 언제

- 날짜: 2026-08-12
- 관련 ADR: ADR 0008 (차원 모델링)
- 이 측정 직전에 무엇을 바꿨나: dimensional_model_etl DAG 신규 추가
  (dim_date/dim_product/dim_user + fact_events, Type 2 SCD)

## 실행 조건

- 스크립트: Airflow `dimensional_model_etl` DAG 수동 실행
- 목표 VU: 해당 없음
- 지속 시간: 해당 없음
- 실행 환경: 로컬 Docker Compose, Spark Streaming 실행 중

## 결과 요약

| 항목 | 값 |
|---|---|
| fact_events 적재 | 성공 (view/add_to_cart/purchase 등 여러 event_type 혼재 확인) |
| revenue 규칙 | purchase만 값 있음, 그 외 0 (정상) |
| dim_product is_current | 전부 true (변경 이력 없어 정상) |
| date_key 형식 | YYYYMMDD 정확 |

## 관찰된 병목

없음. 데이터 없이 DAG만 실행하면 모든 태스크가 "대상 0건"으로
에러 없이 조용히 끝나므로, 검증을 위해서는 상품/유저 적재 +
Spark Streaming 실행 + 이벤트 발생이 선행되어야 함을 확인.

## 다음 액션

- ADR 0009 (데이터 품질 검증, Great Expectations) 구현으로 이동

## Related

- Related ADRs: ADR 0008 (차원 모델링)
- 이전 기록: 010-ci-integration-tests.md
