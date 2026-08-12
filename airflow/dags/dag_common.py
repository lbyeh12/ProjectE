"""
airflow/dags/dag_common.py

세 DAG(daily_etl, data_quality_check, dimensional_model_etl)이 공유하는
재시도/알림 설정 (adrs/0010-airflow-pipeline-reliability.md).

이 파일 자체는 DAG을 정의하지 않는다 - Airflow의 DAG 파서가 dags_folder
안의 모든 .py 파일을 훑지만, DAG 객체가 없는 파일은 그냥 건너뛰므로
헬퍼 모듈을 같은 폴더에 두는 건 안전하다.
"""
import os
from datetime import timedelta

import requests

# 일시적 장애(DB 커넥션 순간 끊김 등)는 재시도로 자동 복구되게 한다.
# 각 태스크가 재실행돼도 안전하도록(멱등) 이미 짜여 있다 -
# INSERT ... ON CONFLICT DO NOTHING, CREATE TABLE IF NOT EXISTS 등.
DEFAULT_ARGS = {
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}


def notify_failure_slack(context):
    """
    재시도까지 전부 실패했을 때 Slack으로 알린다.

    SLACK_WEBHOOK_URL 환경변수가 없으면(예: 이 프로젝트를 그대로
    클론해서 Slack 계정 없이 돌려보는 경우) 콘솔 로그만 남기고
    조용히 넘어간다 - 웹훅 설정을 필수로 강제하지 않는다.
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    dag_id = context["dag"].dag_id
    task_id = context["task_instance"].task_id
    ds = context.get("ds", "unknown")
    message = f":x: Airflow 태스크 실패 (재시도 모두 소진): {dag_id}.{task_id} (날짜: {ds})"

    if not webhook_url:
        print(f"[notify_failure_slack] SLACK_WEBHOOK_URL 미설정, 콘솔에만 남김: {message}")
        return

    try:
        requests.post(webhook_url, json={"text": message}, timeout=5)
    except Exception as e:
        # 알림 전송 자체가 실패해도 DAG 실행 결과에는 영향을 주지 않는다
        # (이미 태스크는 실패로 끝난 뒤의 "알리는" 단계이므로, 여기서
        # 또 예외를 던지면 오히려 다른 문제를 만들 뿐이다).
        print(f"[notify_failure_slack] Slack 전송 실패(무시하고 계속): {e}")
