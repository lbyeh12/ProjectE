# 004: cAdvisor 도입 시도 및 제거

## 언제

- 날짜: 2026-08-08
- 배경: docs/perf/003-worker-scaling.md에서 CPU 포화 여부를 눈으로 볼
  수단이 없어 매번 수동으로 `docker stats`를 실행해야 했다. Docker+
  Prometheus 조합의 표준 도구인 cAdvisor를 추가해서 Grafana에서 상시
  관찰하려 했다.

## 시도한 것

- `docker-compose.yml`에 cAdvisor 서비스 추가, Prometheus가 스크랩
- Grafana 대시보드에 컨테이너별 CPU/메모리 패널 2개 추가
  (`container_cpu_usage_seconds_total{name=~"projecte-.*"}` 등)

## 관찰된 사실

- 대시보드에 두 패널 모두 No data로 나왔다.
- `curl http://localhost:8085/metrics`로 cAdvisor가 실제로 메트릭을
  내보내는지 직접 확인한 결과, 데이터는 정상적으로 있었으나
  **`name` 라벨 자체가 존재하지 않았다.** 컨테이너는
  `id="/docker/<64자리 해시>"` 형태로만 식별됐다.
- `container_label_*` 형태의 라벨도 전혀 없었다
  (`grep "container_label"` 결과 없음).
- Docker 소켓을 디렉토리 단위(`/var/run:/var/run:ro`)에서 파일
  단위(`/var/run/docker.sock:/var/run/docker.sock:ro`)로 명시적으로
  바꿔서 재시도했으나 증상이 동일했다.

## 결론

cAdvisor가 컨테이너 ID를 사람이 읽을 수 있는 이름으로 해석하려면
Docker API(소켓)에 접근해서 컨테이너 목록/이름을 조회해야 하는데,
이 환경(Mac Docker Desktop, LinuxKit VM)에서는 소켓 마운트 방식을
바꿔도 이 조회가 되지 않는 것으로 판단된다. 이는 Mac Docker Desktop
환경에서 흔히 보고되는 제약으로 보인다.

**개별 컨테이너를 구분할 수 없는 상태의 cAdvisor는 실용성이 없다고
판단해 제거하기로 결정했다.** 어차피 Docker Desktop 앱 자체의
Containers 탭에서 컨테이너별 CPU/메모리를 실시간으로 볼 수 있어서,
같은 정보를 못 보여주는 도구를 추가로 운영할 이유가 없다.

## 되돌린 것

- `docker-compose.yml`: cadvisor 서비스 제거
- `monitoring/prometheus/prometheus.yml`: cadvisor 스크랩 타겟 제거
- `monitoring/grafana/dashboards/fastapi-overview.json`: CPU/메모리
  패널 2개 제거

## 대안

- 전체적인 CPU/메모리 경향 확인: Docker Desktop 앱의 Containers 탭
- 특정 시점(예: EOF 재현 시)의 컨테이너별 정확한 사용량: 그 순간
  `docker stats --no-stream` 수동 실행 (이전 라운드들에서 이미 이
  방식으로 확인한 적 있음)

## Related

- Related ADRs: ADR 0001(모니터링 도구 선정)
- 관련 perf 기록: docs/perf/003-worker-scaling.md
