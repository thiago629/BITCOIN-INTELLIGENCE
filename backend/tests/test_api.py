from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import (
    ADDR,
    ADDRESS_PAYLOAD,
    BLOCK_HASH,
    BLOCKSTREAM,
    MEMPOOL,
    MEMPOOL_PAYLOAD,
    TXID,
    FakeUpstream,
    block_payload,
    tx_payload,
)


def test_recent_blocks_envelope(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.json(MEMPOOL, "/api/v1/blocks", [block_payload(h, extras=True) for h in (12, 11, 10)])
    r = client.get("/api/v1/blocks/recent")
    assert r.status_code == 200
    body = r.json()
    assert [b["height"] for b in body["data"]] == [12, 11, 10]
    assert body["meta"]["source"] == "mempool.space"
    assert body["meta"]["fetched_at"].endswith("Z")


def test_block_by_height_resolves_hash(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.text(MEMPOOL, "/api/block-height/10", BLOCK_HASH)
    upstream.json(
        MEMPOOL, f"/api/v1/block/{BLOCK_HASH}", block_payload(10, extras=True, hash_=BLOCK_HASH)
    )
    r = client.get("/api/v1/blocks/height/10")
    assert r.status_code == 200 and r.json()["data"]["hash"] == BLOCK_HASH


def test_transaction_and_validation(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.json(MEMPOOL, f"/api/tx/{TXID}", tx_payload())
    assert client.get(f"/api/v1/tx/{TXID}").json()["data"]["fee_sat"] == 1000
    assert client.get("/api/v1/tx/not-a-txid").status_code == 422
    assert client.get("/api/v1/tx/" + "zz" * 32).status_code == 422


def test_not_found_maps_to_404(client: TestClient) -> None:
    r = client.get("/api/v1/tx/" + "e" * 64)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_upstream_down_maps_to_503_without_data(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.status(MEMPOOL, "/api/blocks/tip/height", 500)
    upstream.status(BLOCKSTREAM, "/api/blocks/tip/height", 500)
    r = client.get("/api/v1/network/tip")
    assert r.status_code == 503
    body = r.json()
    assert "data" not in body
    assert body["error"]["code"] == "upstream_unavailable"
    assert len(body["error"]["details"]) == 2


def test_address_endpoints(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.json(MEMPOOL, f"/api/address/{ADDR}", ADDRESS_PAYLOAD)
    upstream.json(MEMPOOL, f"/api/address/{ADDR}/txs", [tx_payload()])
    assert (
        client.get(f"/api/v1/address/{ADDR}").json()["data"]["confirmed_balance_sat"] == 150_000_000
    )
    txs = client.get(f"/api/v1/address/{ADDR}/txs").json()["data"]
    assert txs[0]["net_sat"] == -100_001_000
    assert client.get("/api/v1/address/not_an_address").status_code == 422
    assert (
        client.get("/api/v1/address/bc1QAR0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq").status_code == 422
    )


def test_network_summary_is_partial_when_a_section_fails(
    client: TestClient, upstream: FakeUpstream
) -> None:
    upstream.text(MEMPOOL, "/api/blocks/tip/height", "900000")
    upstream.json(MEMPOOL, "/api/mempool", MEMPOOL_PAYLOAD)
    upstream.json(
        MEMPOOL,
        "/api/v1/fees/recommended",
        {"fastestFee": 5, "halfHourFee": 4, "hourFee": 3, "economyFee": 2, "minimumFee": 1},
    )
    upstream.status(MEMPOOL, "/api/v1/difficulty-adjustment", 500)
    body = client.get("/api/v1/network/summary").json()
    assert body["tip_height"]["data"] == 900000
    assert body["fees"]["data"]["method"] == "recommended"
    assert body["mempool"]["data"]["count"] == 1000
    assert body["difficulty"]["data"] is None and "difficulty" in body["difficulty"]["error"]


def test_search(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.text(MEMPOOL, "/api/block-height/10", BLOCK_HASH)
    upstream.json(MEMPOOL, f"/api/tx/{TXID}", tx_payload())
    upstream.json(MEMPOOL, f"/api/v1/block/{BLOCK_HASH}", block_payload(10, hash_=BLOCK_HASH))
    assert client.get("/api/v1/search", params={"q": "10"}).json() == {
        "type": "block",
        "id": BLOCK_HASH,
    }
    assert client.get("/api/v1/search", params={"q": TXID}).json()["type"] == "transaction"
    assert client.get("/api/v1/search", params={"q": BLOCK_HASH}).json()["type"] == "block"
    assert client.get("/api/v1/search", params={"q": ADDR}).json()["type"] == "address"
    assert client.get("/api/v1/search", params={"q": "hello"}).status_code == 422
    assert client.get("/api/v1/search", params={"q": "f" * 64}).status_code == 404


def test_health_and_security_headers(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"]["ok"] is True
    assert [p["key"] for p in body["providers"]] == ["mempool", "blockstream"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Request-ID"]


def test_rate_limit(settings: Settings, upstream: FakeUpstream) -> None:
    settings.rate_limit_per_minute = 3
    with TestClient(create_app(settings, http_transport=upstream.transport)) as c:
        codes = [c.get("/api/v1/health").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_history_endpoints_empty_db(client: TestClient) -> None:
    r = client.get("/api/v1/history/blocks")
    assert r.status_code == 200 and r.json()["data"] == [] and r.json()["meta"]["records"] == 0
    assert client.get("/api/v1/history/network").json()["data"] == []
    assert client.get("/api/v1/history/blocks?limit=0").status_code == 422
