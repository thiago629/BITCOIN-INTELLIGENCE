import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.models import BlockRecord, WhaleScannedBlock, WhaleTx
from app.db.session import Database
from app.main import create_app
from tests.conftest import MEMPOOL, FakeUpstream, tx_payload

SATS = 100_000_000
NOW = datetime.now(UTC)


def seed(settings: Settings, covered_hours: float | None = 30) -> None:
    async def run() -> None:
        db = Database(settings.database_url)
        await db.create_all()
        async with db.session() as s:
            if covered_hours is not None:
                # Oldest analysed block -> defines the coverage window.
                s.add(
                    BlockRecord(
                        height=1,
                        hash="e" * 64,
                        timestamp=NOW - timedelta(hours=covered_hours),
                        tx_count=1,
                        size=1,
                        weight=1,
                        source="t",
                        ingested_at=NOW,
                    )
                )
                s.add(
                    WhaleScannedBlock(
                        height=1,
                        hash="e" * 64,
                        tx_count=1,
                        whale_count=0,
                        scanned_at=NOW,
                        source="t",
                    )
                )
            for i, (btc, confirmed, hours_ago) in enumerate(
                [(150, True, 1), (2_500, True, 2), (12_000, False, 0.1), (400, True, 50)]
            ):
                t = NOW - timedelta(hours=hours_ago)
                s.add(
                    WhaleTx(
                        txid=f"{i:064x}",
                        value_sat=btc * SATS,
                        fee_sat=1000,
                        vsize=200,
                        confirmed=confirmed,
                        block_height=900 + i if confirmed else None,
                        block_hash=None,
                        block_time=t if confirmed else None,
                        first_seen_at=t,
                        event_time=t,
                        detected_via="block" if confirmed else "mempool",
                        source="mempool.space",
                        enriched=False,
                        upstream_missing=False,
                    )
                )
            await s.commit()
        await db.dispose()

    asyncio.run(run())


def test_list_filters_sort_and_tracking(settings: Settings, upstream: FakeUpstream) -> None:
    seed(settings)
    with TestClient(create_app(settings, http_transport=upstream.transport)) as c:
        body = c.get("/api/v1/whales").json()
        assert body["total"] == 4 and body["source"] == "database"
        assert body["data"][0]["txid"] == f"{2:064x}"  # newest first
        assert body["tracking"]["min_btc"] == 100 and len(body["tracking"]["notes"]) == 3

        by_value = c.get("/api/v1/whales", params={"sort": "value"}).json()["data"]
        assert [w["value_sat"] // SATS for w in by_value] == [12_000, 2_500, 400, 150]
        assert by_value[0]["tier"]["label"] == "Ballena"

        r = c.get("/api/v1/whales", params={"min_btc": 300, "max_btc": 5000}).json()
        assert sorted(w["value_sat"] // SATS for w in r["data"]) == [400, 2_500]
        r = c.get("/api/v1/whales", params={"status": "unconfirmed"}).json()
        assert r["total"] == 1 and r["data"][0]["confirmed"] is False
        since = (NOW - timedelta(hours=24)).isoformat()
        assert c.get("/api/v1/whales", params={"since": since}).json()["total"] == 3
        page = c.get("/api/v1/whales", params={"limit": 2, "offset": 2}).json()
        assert len(page["data"]) == 2 and page["total"] == 4

        assert c.get("/api/v1/whales", params={"min_btc": 10, "max_btc": 5}).status_code == 422
        assert c.get("/api/v1/whales", params={"status": "bogus"}).status_code == 422


def test_stats(settings: Settings, upstream: FakeUpstream) -> None:
    seed(settings)
    with TestClient(create_app(settings, http_transport=upstream.transport)) as c:
        s = c.get("/api/v1/whales/stats", params={"hours": 24}).json()
    assert s["count"] == 3 and s["unconfirmed_count"] == 1
    assert s["volume_sat"] == (150 + 2_500 + 12_000) * SATS
    assert s["largest"]["value_sat"] == 12_000 * SATS
    assert sum(b["count"] for b in s["by_hour"]) == 3
    assert [t["count"] for t in s["by_tier"]] == [1, 1, 1]


def test_detail_enriches_on_demand(settings: Settings, upstream: FakeUpstream) -> None:
    seed(settings)
    txid = f"{1:064x}"
    payload = tx_payload()
    payload["txid"] = txid
    upstream.json(MEMPOOL, f"/api/tx/{txid}", payload)
    with TestClient(create_app(settings, http_transport=upstream.transport)) as c:
        d = c.get(f"/api/v1/whales/{txid}").json()
        assert d["whale"]["enriched"] is True and d["whale"]["input_count"] == 1
        layers = d["analysis"]
        assert {"observed", "interpretations", "unknowns"} <= set(layers)
        assert any(f["label"] == "Identidad de los propietarios" for f in layers["unknowns"])
        # Cached in DB: second call does not hit upstream again.
        calls = upstream.count(MEMPOOL, f"/api/tx/{txid}")
        c.get(f"/api/v1/whales/{txid}")
        assert upstream.count(MEMPOOL, f"/api/tx/{txid}") == calls
        assert c.get(f"/api/v1/whales/{'f' * 64}").status_code == 404
        assert c.get("/api/v1/whales/nothex").status_code == 422


# ------------------------------------------------------------------ alerts


def test_alert_rule_crud_and_validation(client: TestClient) -> None:
    r = client.post(
        "/api/v1/alerts/rules", json={"name": "  Grandes   movimientos ", "min_btc": 500}
    )
    assert r.status_code == 201
    rule = r.json()
    assert rule["name"] == "Grandes movimientos" and rule["enabled"] and rule["events_count"] == 0

    assert client.post("/api/v1/alerts/rules", json={"name": "x", "min_btc": 10}).status_code == 422
    assert (
        client.post("/api/v1/alerts/rules", json={"name": "   ", "min_btc": 500}).status_code == 422
    )
    assert client.post("/api/v1/alerts/rules", json={"name": "x", "min_btc": -1}).status_code == 422

    p = client.patch(f"/api/v1/alerts/rules/{rule['id']}", json={"enabled": False, "min_btc": 1000})
    assert p.status_code == 200 and p.json()["enabled"] is False and p.json()["min_btc"] == 1000
    assert (
        client.patch(f"/api/v1/alerts/rules/{rule['id']}", json={"min_btc": 1}).status_code == 422
    )
    assert client.patch("/api/v1/alerts/rules/999", json={"enabled": True}).status_code == 404

    assert len(client.get("/api/v1/alerts/rules").json()) == 1
    assert client.delete(f"/api/v1/alerts/rules/{rule['id']}").status_code == 204
    assert client.get("/api/v1/alerts/rules").json() == []
    assert client.delete(f"/api/v1/alerts/rules/{rule['id']}").status_code == 404
    assert client.get("/api/v1/alerts/events").json()["total"] == 0


def test_writes_require_key_outside_development(settings: Settings, upstream: FakeUpstream) -> None:
    settings.environment = "production"
    with TestClient(create_app(settings, http_transport=upstream.transport)) as c:
        r = c.post("/api/v1/alerts/rules", json={"name": "a", "min_btc": 500})
        assert r.status_code == 403
        assert c.get("/api/v1/alerts/rules").status_code == 200  # reads stay open

    settings.admin_api_key = "s3cret-key"
    with TestClient(create_app(settings, http_transport=upstream.transport)) as c:
        body = {"name": "a", "min_btc": 500}
        assert c.post("/api/v1/alerts/rules", json=body).status_code == 401
        assert (
            c.post("/api/v1/alerts/rules", json=body, headers={"X-API-Key": "nope"}).status_code
            == 401
        )
        ok = c.post("/api/v1/alerts/rules", json=body, headers={"X-API-Key": "s3cret-key"})
        assert ok.status_code == 201


def test_stats_marks_uncovered_hours_as_unknown(settings: Settings, upstream: FakeUpstream) -> None:
    seed(settings, covered_hours=3)
    with TestClient(create_app(settings, http_transport=upstream.transport)) as c:
        s = c.get("/api/v1/whales/stats", params={"hours": 24}).json()
    assert s["tracking"]["coverage_since"] is not None
    known = [b for b in s["by_hour"] if b["count"] is not None]
    unknown = [b for b in s["by_hour"] if b["count"] is None]
    # Only the last ~3 hours are covered; earlier hours are unknown, not zero.
    assert 2 <= len(known) <= 4 and len(unknown) >= 20
