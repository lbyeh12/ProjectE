# 013: DAG 간 의존성을 센서에서 체인 방식으로 전환

## 언제

- 날짜: 2026-08-12
- 관련 ADR: ADR 0009, ADR 0011
- 이 측정 직전에 무엇을 바꿨나: dimensional_model_etl, export_to_s3의
  ExternalTaskSensor를 TriggerDagRunOperator 체인으로 교체.

## 실행 조건

- 스크립트: Airflow DAG 수동 트리거
- 실행 환경: 로컬 Docker Compose

## 결과 요약

| 방식 | 문제 |
|---|---|
| ExternalTaskSensor (수정 전) | 두 DAG을 수동으로 각각 다른 시각에 트리거하면 logical_date가 안 맞아 센서가 타임아웃까지 영원히 대기 |
| execution_date_fn으로 자정 정규화 (1차 수정) | 문제는 완화되나, 여전히 두 DAG을 "각각" 정확한 시각(자정)으로 맞춰 트리거해야 하는 부담이 남음 |
| TriggerDagRunOperator 체인 (최종) | data_quality_check 하나만 트리거하면 dimensional_model_etl → export_to_s3까지 자동으로 이어짐, 시각 맞출 필요 없음 |

## 관찰된 병목

`ExternalTaskSensor`는 스케줄대로(`@daily`) 자동 실행될 때는 문제가
없다 - 같은 스케줄의 여러 DAG이 정확히 같은 자정 logical_date를
공유하기 때문이다. 문제는 사람이 각 DAG을 수동으로, 서로 다른
시각에 트리거하며 테스트할 때만 드러났다. 처음엔 `execution_date_fn`
으로 "그날 자정"에 맞추는 방식으로 완화를 시도했으나, 이것도 결국
data_quality_check 쪽을 정확히 자정으로 트리거해야 하는 제약이
남아 실용적이지 않았다.

근본적으로 "독립된 DAG을 나중에 시각 기준으로 맞춰 연결"하는 접근
자체가 수동 테스트와 잘 안 맞는다는 걸 확인했다.
TriggerDagRunOperator로 "끝나면 다음을 직접 실행시키는" 체인 방식
으로 바꾸니 이 문제가 구조적으로 사라졌다 - 맨 앞 DAG 하나만
트리거하면 나머지가 자동으로 이어지고, 로컬 개발/테스트 경험이
크게 개선됐다.

## 다음 액션

- AWS 자격증명 설정 후 export_to_s3 전체 체인 재검증
- Glue Crawler, Athena 연동으로 이동

## Related

- Related ADRs: ADR 0009 (데이터 품질 검증), ADR 0011 (AWS 클라우드 연동)
- 이전 기록: 012-great-expectations-version-conflict.md
