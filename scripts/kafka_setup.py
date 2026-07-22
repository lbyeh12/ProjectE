"""
Kafka 연결 확인 및 토픽 생성 스크립트.

docker compose up -d 로 Kafka가 뜬 뒤 실행한다.
KAFKA_AUTO_CREATE_TOPICS_ENABLE=true 라서 토픽은 자동 생성되지만,
파티션 수를 명시적으로 지정하고 싶을 때 이 스크립트로 미리 만든다.

실행:
    python scripts/kafka_setup.py
"""
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

BOOTSTRAP_SERVERS = "localhost:9092"

# 초기에는 단일 토픽으로 시작하고 event_type 으로 구분한다.
# (추후 트래픽/처리 로직이 복잡해지면 purchase-events, search-events 로 분리)
TOPICS = [
    NewTopic(name="user-events", num_partitions=3, replication_factor=1),
]


def main():
    print(f"Kafka 연결 시도: {BOOTSTRAP_SERVERS}")
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP_SERVERS)

    for topic in TOPICS:
        try:
            admin.create_topics([topic])
            print(f"  토픽 생성: {topic.name} (파티션 {topic.num_partitions})")
        except TopicAlreadyExistsError:
            print(f"  토픽 이미 존재: {topic.name}")

    print("\n현재 토픽 목록:")
    for name in sorted(admin.list_topics()):
        print(f"  - {name}")

    admin.close()
    print("\n완료.")


if __name__ == "__main__":
    main()
