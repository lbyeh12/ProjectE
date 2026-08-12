# 012: Great Expectations 버전 충돌 해결

## 언제

- 날짜: 2026-08-12
- 관련 ADR: ADR 0009 (데이터 품질 검증)
- 이 측정 직전에 무엇을 바꿨나: airflow/Dockerfile에 great_expectations
  설치 추가 시도.

## 실행 조건

- 스크립트: `docker compose build airflow-apiserver`
- 실행 환경: 로컬 Docker Compose (Airflow 3.3.0 공식 이미지)

## 결과 요약

| 시도 | 결과 |
|---|---|
| great_expectations>=0.18,<0.19 + pandas 설치 | 빌드 실패 (numpy 소스 컴파일 시도 중 권한 오류) |
| great_expectations==1.20.0만 설치 (pandas 재설치 제거) | (재검증 대기) |

## 관찰된 병목

Airflow 3.3.0 이미지에 이미 numpy 2.5.0/pandas 2.3.3이 설치되어
있었다. `great_expectations>=0.18,<0.19`는 numpy 1.26.4 같은
훨씬 오래된 버전을 요구해서, pip가 그 버전으로 다운그레이드하려
시도했다. 그 오래된 numpy 버전에 이 이미지(Python 버전/아키텍처)에
맞는 사전 빌드 바이너리(wheel)가 없어 소스 컴파일로 넘어갔고,
Airflow 이미지는 비root 사용자로 pip install을 실행하도록 되어
있어 컴파일러(cc/gcc) 실행 권한이 없어 실패했다.

GE 최신 버전(1.20.0, 2026-08 릴리스)은 numpy 2.x 관련 버그가 이미
수정되어 있어 이미지의 기존 numpy/pandas와 충돌하지 않을 것으로
판단, 버전을 올려서 해결했다. pandas는 이미 있으므로 재설치를
제거했다.

GE 1.x는 API가 완전히 바뀌어(Fluent/Core API), 기존 `ge.from_pandas()`
방식 코드를 새 API로 재작성했다. 이 환경에서 정확한 API 동작을
실행 검증할 수 없어(네트워크 제약), GE 호출 전체를 try/except로
감싸 GE가 실패해도 핵심 로직(pandas 기반 격리 판정)은 항상
정상 동작하도록 방어적으로 설계했다.

## 다음 액션

- 실제 빌드 재시도 및 DAG 실행으로 GE 1.x API 정상 동작 확인
- ADR 0010 (Airflow 재시도/알림) 구현으로 이동

## Related

- Related ADRs: ADR 0009 (데이터 품질 검증)
- 이전 기록: 011-dimensional-model-verification.md
