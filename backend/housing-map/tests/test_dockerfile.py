from pathlib import Path


DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_startup_seeds_market_reference_when_a_persisted_volume_lacks_it():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY data/market_reference.json ./seed-data/market_reference.json" in dockerfile
    assert "[ ! -f /app/data/market_reference.json ]" in dockerfile
    assert "cp /app/seed-data/market_reference.json /app/data/" in dockerfile
