from app.domain.models import Transaction, TxInput, TxOutput, TxStatus
from app.whales.analysis import SATS, WhaleFacts, analyse, build_tiers, enrich, tier_for

TIERS = build_tiers([1000, 100, 10_000])


def labels(findings: list) -> list[str]:  # type: ignore[type-arg]
    return [f.label for f in findings]


def test_tiers_sorted_and_classified() -> None:
    assert [t.min_btc for t in TIERS] == [100, 1000, 10_000]
    assert tier_for(99 * SATS, TIERS) is None
    assert tier_for(100 * SATS, TIERS).level == 1  # type: ignore[union-attr]
    assert tier_for(5_000 * SATS, TIERS).label == "Muy grande"  # type: ignore[union-attr]
    assert tier_for(20_000 * SATS, TIERS).level == 3  # type: ignore[union-attr]


def make_tx(
    inputs: list[tuple[str | None, int]], outputs: list[tuple[str | None, int]]
) -> Transaction:
    return Transaction(
        txid="a" * 64,
        version=2,
        locktime=0,
        size=300,
        weight=1200,
        vsize=300,
        fee_sat=1000,
        status=TxStatus(confirmed=True, block_height=1),
        inputs=[
            TxInput(prev_txid="b" * 64, prev_vout=0, address=a, value_sat=v) for a, v in inputs
        ],
        outputs=[TxOutput(index=i, address=a, value_sat=v) for i, (a, v) in enumerate(outputs)],
        total_input_sat=sum(v for _, v in inputs),
        total_output_sat=sum(v for _, v in outputs),
    )


def test_enrich_detects_value_returned_to_input_address() -> None:
    tx = make_tx([("A", 500 * SATS)], [("B", 120 * SATS), ("A", 380 * SATS - 1000)])
    e = enrich(tx)
    assert e.input_count == 1 and e.output_count == 2
    assert e.returned_to_input_sat == 380 * SATS - 1000
    assert e.largest_output_sat == 380 * SATS - 1000


def facts(**kw: object) -> WhaleFacts:
    base: dict[str, object] = dict(
        value_sat=500 * SATS, fee_sat=1000, confirmed=True, block_height=10, enriched=True
    )
    base.update(kw)
    return WhaleFacts(**base)  # type: ignore[arg-type]


def test_unknowns_always_include_identity_and_real_amount() -> None:
    for f in (facts(enriched=False), facts(input_count=1, output_count=2)):
        a = analyse(f)
        assert "Identidad de los propietarios" in labels(a.unknowns)
        assert "Importe económico real transferido" in labels(a.unknowns)


def test_not_enriched_has_no_interpretations() -> None:
    a = analyse(facts(enriched=False))
    assert a.interpretations == []
    assert "Estructura de entradas y salidas" in labels(a.unknowns)


def test_consolidation_and_batch_heuristics_are_interpretations_with_method() -> None:
    a = analyse(
        facts(input_count=40, output_count=1, input_address_count=12, output_address_count=1)
    )
    assert "Posible consolidación de fondos" in labels(a.interpretations)
    b = analyse(
        facts(input_count=1, output_count=50, input_address_count=1, output_address_count=50)
    )
    batch = next(f for f in b.interpretations if f.label == "Posible pago en lote")
    assert batch.method and batch.confidence == "media"
    # Heuristics never leak into the observed layer.
    assert not any("Posible" in label for label in labels(a.observed + b.observed))


def test_returned_value_yields_new_amount_estimate() -> None:
    a = analyse(facts(input_count=1, output_count=2, returned_to_input_sat=400 * SATS))
    assert "Salidas a direcciones de origen" in labels(a.observed)
    est = next(f for f in a.interpretations if f.label == "Importe nuevo estimado")
    assert "100 BTC" in est.detail and est.confidence == "alta"
    assert "Posible pago con cambio" not in labels(a.interpretations)


def test_upstream_missing() -> None:
    a = analyse(facts(enriched=False, confirmed=False, block_height=None, upstream_missing=True))
    assert "Transacción no localizada en la fuente" in labels(a.unknowns)
    assert "Sin confirmar" in a.observed[1].detail


def test_amounts_use_spanish_format_and_exact_satoshis() -> None:
    a = analyse(facts(value_sat=2_001_043_798_980, fee_sat=1_400))
    assert a.observed[0].detail.startswith("20.010,4379898 BTC")
    assert any(f.detail == "0,000014 BTC" for f in a.observed)
