#!/bin/bash
# ============================================================
# Spark Streaming 잡 실행 스크립트
#
# Kafka 커넥터 + PostgreSQL JDBC 드라이버를 --packages 로 받아서 실행한다.
# (이 jar들은 pip 로 설치되지 않으므로 spark-submit 실행 시점에 받는다.
#  최초 1회는 다운로드 때문에 느리고, 이후엔 캐시되어 빠르다.)
#
# 사전 조건:
#   1. Java 17 설치됨 (brew install openjdk@17) — 이 스크립트가 자동으로 잡음
#   2. venv-spark 활성화 (pip install -r requirements-spark.txt)
#   3. docker compose 로 Kafka, PostgreSQL 실행 중
#
# 사용:
#   bash spark/run_streaming.sh
# ============================================================
set -e

# --- Java 17 설정 ---
# Spark 4.0.x 는 Java 17/21 을 지원하지만, 이 프로젝트는 Java 17 로 고정한다.
# 아래 후보 경로를 순서대로 확인해서 처음 발견되는 Java 17 을 사용한다.
# (시스템 기본이 Java 21 이어도 Spark 실행에만 17 을 적용)
JAVA17_HOME=""
for candidate in \
  "/opt/homebrew/opt/openjdk@17" \
  "/usr/local/opt/openjdk@17" \
  "$(/usr/libexec/java_home -v 17 2>/dev/null)" \
  "$(brew --prefix openjdk@17 2>/dev/null)"; do
  if [ -n "$candidate" ] && [ -x "$candidate/bin/java" ]; then
    JAVA17_HOME="$candidate"
    break
  fi
done

if [ -z "$JAVA17_HOME" ]; then
  echo "[에러] Java 17 을 찾을 수 없습니다. 'brew install openjdk@17' 로 설치하세요." >&2
  exit 1
fi

export JAVA_HOME="$JAVA17_HOME"
export PATH="$JAVA_HOME/bin:$PATH"

echo "JAVA_HOME=$JAVA_HOME"
echo "사용 중인 Java:"
java -version
echo ""

# 버전은 pyspark 버전(4.0.x)에 맞춰야 한다.
# spark-sql-kafka 의 스칼라 버전(2.13)과 Spark 버전(4.0.4)이 pyspark와 일치해야 함.
SPARK_VERSION="4.0.4"
SCALA_VERSION="2.13"
POSTGRES_JDBC="42.7.4"

PACKAGES="org.apache.spark:spark-sql-kafka-0-10_${SCALA_VERSION}:${SPARK_VERSION},org.postgresql:postgresql:${POSTGRES_JDBC}"

# 스크립트 위치 기준으로 job 파일 경로 잡기
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

spark-submit \
  --packages "${PACKAGES}" \
  "${SCRIPT_DIR}/streaming_job.py"