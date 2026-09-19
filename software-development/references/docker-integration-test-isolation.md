# Docker Integration Test Isolation

When running integration tests against Docker services (Kafka, TimescaleDB, Redis), data persists between test runs causing flaky tests.

## The Problem

- Kafka topics retain messages from previous test runs
- PostgreSQL tables retain rows from previous test runs  
- Tests read stale data from external services, causing assertion failures

## Solution: Autouse Fixture with Cleanup

Add to `tests/conftest.py`:

```python
import pytest
import subprocess

@pytest.fixture(autouse=True)
def clean_services():
    """Clear Kafka topic and DB before each test."""
    # Clear PostgreSQL table
    subprocess.run([
        "docker", "exec", "rankit-timescaledb-1",
        "psql", "-U", "rankit", "-d", "rankit",
        "-c", "DELETE FROM market_data_ohlcv;"
    ], capture_output=True)
    
    # Clear Kafka topic (delete + recreate)
    try:
        subprocess.run([
            "docker", "exec", "rankit-kafka-1",
            "/opt/kafka/bin/kafka-topics.sh",
            "--delete", "--topic", "market.ohlcv.raw",
            "--if-exists", "--bootstrap-server", "localhost:9092"
        ], check=True, capture_output=True)
    except Exception:
        pass
    
    subprocess.run([
        "docker", "exec", "rankit-kafka-1",
        "/opt/kafka/bin/kafka-topics.sh",
        "--create", "--topic", "market.ohlcv.raw",
        "--partitions", "1", "--replication-factor", "1",
        "--bootstrap-server", "localhost:9092"
    ], capture_output=True)
    
    yield
```

## Alternative: Consumer Offset Strategy

For Kafka-only tests, use unique consumer groups with `latest` offset + seek to beginning:

```python
consumer = AIOKafkaConsumer(
    "topic",
    bootstrap_servers="localhost:9092",
    auto_offset_reset="latest",  # Start at end
    group_id=f"test-{uuid.uuid4()}",  # Unique per test
)
await consumer.start()
await asyncio.sleep(0.5)  # Wait for messages to commit
for partition in consumer.assignment():
    await consumer.seek_to_beginning(partition)  # Now read from test start
```

## Key Takeaways

- Always use `autouse=True` for cleanup fixtures in integration tests
- Delete Kafka topics (not just consume) — offsets persist
- Clear DB tables explicitly — upserts can leave stale data
- Each test should be independent; no shared state between runs