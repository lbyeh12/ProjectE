#!/bin/bash
# ============================================================
# Spark Streaming 잡 실행 스크립트
#
# Kafka 커넥터 + PostgreSQL JDBC 드라이버를 --packages 로 받아서 실행한다.
# (이 jar들은 pip 로 설치되지 않으므로 spark-submit 실행 시점에 받는다.
#  최초 1회는 다운로드 때문에 느리고, 이후엔 캐시되어 빠르다.)
#
# 사전 조건:
#   1. Java(JVM) 설치됨 (java -version 확인)
#   2. venv-spark 활성화 (pip install -r requirements-spark.txt)
#   3. docker compose 로 Kafka, PostgreSQL 실행 중
#
# 사용:
#   bash spark/run_streaming.sh
# ============================================================
set -e

# --- Java 17 자동 설정 ---
# Spark 3.5.x 는 Java 8/11/17 만 지원한다 (Java 21+ 불가).
# 시스템 기본이 Java 21 이어도, brew로 설치한 openjdk@17 을 Spark에만 쓰도록 지정.
if [ -z "$JAVA_HOME" ] || ! "$JAVA_HOME/bin/java" -version 2>&1 | grep -q "17\."; then
  for candidate in \
    "$(/usr/libexec/java_home -v 17 2>/dev/null)" \
    "$(brew --prefix openjdk@17 2>/dev/null)" \
    "/opt/homebrew/opt/openjdk@17" \
    "/usr/local/opt/openjdk@17"; do
    if [ -n "$candidate" ] && [ -x "$candidate/bin/java" ]; then
      export JAVA_HOME="$candidate"
      export PATH="$JAVA_HOME/bin:$PATH"
      break
    fi
  done
fi

echo "사용 중인 Java:"
java -version
echo ""

# 버전은 pyspark 버전에 맞춰야 한다.
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