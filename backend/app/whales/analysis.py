"""Whale movement analysis: classification and evidence layers.

Every finding is placed in exactly one layer:

* ``observed``      — facts read directly from the blockchain.
* ``interpretation``— heuristic readings of those facts, each with the method
                      used and a confidence level. Never presented as facts.
* ``unknown``       — what the data cannot tell us.

No function in this module attributes identities to addresses.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from app.domain.models import Transaction

SATS = 100_000_000
TIER_NAMES = ["Grande", "Muy grande", "Ballena", "Ballena excepcional"]

Confidence = Literal["baja", "media", "alta"]


class Tier(BaseModel):
    level: int  # 1 = lowest tracked tier
    min_btc: float
    label: str


def build_tiers(thresholds_btc: list[float]) -> list[Tier]:
    ordered = sorted(set(thresholds_btc))
    return [
        Tier(
            level=i + 1,
            min_btc=t,
            label=TIER_NAMES[i] if i < len(TIER_NAMES) else f"Nivel {i + 1}",
        )
        for i, t in enumerate(ordered)
    ]


def tier_for(value_sat: int, tiers: list[Tier]) -> Tier | None:
    match: Tier | None = None
    for tier in tiers:
        if value_sat >= tier.min_btc * SATS:
            match = tier
    return match


@dataclass(frozen=True)
class Enrichment:
    input_count: int
    output_count: int
    input_sum_sat: int | None
    largest_output_sat: int
    input_address_count: int
    output_address_count: int
    returned_to_input_sat: int
    unknown_address_output_count: int


def enrich(tx: Transaction) -> Enrichment:
    """Derive observable statistics from a full transaction."""
    input_addresses = {i.address for i in tx.inputs if i.address}
    output_addresses = {o.address for o in tx.outputs if o.address}
    returned = sum(o.value_sat for o in tx.outputs if o.address and o.address in input_addresses)
    return Enrichment(
        input_count=len(tx.inputs),
        output_count=len(tx.outputs),
        input_sum_sat=tx.total_input_sat,
        largest_output_sat=max((o.value_sat for o in tx.outputs), default=0),
        input_address_count=len(input_addresses),
        output_address_count=len(output_addresses),
        returned_to_input_sat=returned,
        unknown_address_output_count=sum(1 for o in tx.outputs if not o.address and o.value_sat),
    )


class Finding(BaseModel):
    label: str
    detail: str
    method: str | None = None
    confidence: Confidence | None = None


class Analysis(BaseModel):
    observed: list[Finding]
    interpretations: list[Finding]
    unknowns: list[Finding]


@dataclass
class WhaleFacts:
    """Minimal view of a stored whale used by :func:`analyse` (keeps it pure)."""

    value_sat: int
    fee_sat: int | None
    confirmed: bool
    block_height: int | None
    enriched: bool
    input_count: int | None = None
    output_count: int | None = None
    input_sum_sat: int | None = None
    largest_output_sat: int | None = None
    input_address_count: int | None = None
    output_address_count: int | None = None
    returned_to_input_sat: int | None = None
    unknown_address_output_count: int | None = None
    upstream_missing: bool = False


def _btc(sat: int) -> str:
    """Spanish number format (matches the UI): 20.010,43798 BTC."""
    sign = "-" if sat < 0 else ""
    whole, frac = divmod(abs(sat), SATS)
    frac_s = f"{frac:08d}".rstrip("0")
    whole_s = f"{whole:,}".replace(",", ".")
    return f"{sign}{whole_s}{',' + frac_s if frac_s else ''} BTC"


def analyse(w: WhaleFacts) -> Analysis:
    observed: list[Finding] = [
        Finding(
            label="Importe total de salidas",
            detail=f"{_btc(w.value_sat)} (suma de todas las salidas, incluido el posible cambio).",
        ),
        Finding(
            label="Estado",
            detail=(
                f"Confirmada en el bloque {w.block_height}."
                if w.confirmed and w.block_height is not None
                else "Sin confirmar: vista en el mempool, todavía no incluida en un bloque."
            ),
        ),
    ]
    if w.fee_sat is not None:
        observed.append(Finding(label="Comisión pagada", detail=_btc(w.fee_sat)))

    interpretations: list[Finding] = []
    unknowns: list[Finding] = [
        Finding(
            label="Identidad de los propietarios",
            detail="Las direcciones no revelan quién las controla. "
            "Bitcoin Intelligence no atribuye identidades sin pruebas verificables.",
        ),
        Finding(
            label="Importe económico real transferido",
            detail="Bitcoin no marca qué salida es cambio. El importe que cambió de manos "
            "puede ser bastante menor que el total de salidas.",
        ),
    ]

    if w.upstream_missing:
        unknowns.append(
            Finding(
                label="Transacción no localizada en la fuente",
                detail="La fuente de datos ya no encuentra esta transacción. Puede haber sido "
                "reemplazada o expulsada del mempool antes de confirmarse.",
            )
        )
        return Analysis(observed=observed, interpretations=interpretations, unknowns=unknowns)

    if not w.enriched or w.input_count is None or w.output_count is None:
        unknowns.append(
            Finding(
                label="Estructura de entradas y salidas",
                detail="Aún no se ha analizado el detalle de la transacción. "
                "Se completa automáticamente en los próximos ciclos.",
            )
        )
        return Analysis(observed=observed, interpretations=interpretations, unknowns=unknowns)

    observed.append(
        Finding(
            label="Estructura",
            detail=f"{w.input_count} entradas ({w.input_address_count} direcciones distintas) → "
            f"{w.output_count} salidas ({w.output_address_count} direcciones distintas).",
        )
    )
    if w.largest_output_sat is not None:
        share = w.largest_output_sat / w.value_sat * 100 if w.value_sat else 0
        observed.append(
            Finding(
                label="Mayor salida individual",
                detail=f"{_btc(w.largest_output_sat)} ({share:.1f} % del total de salidas).",
            )
        )
    returned = w.returned_to_input_sat or 0
    if returned:
        observed.append(
            Finding(
                label="Salidas a direcciones de origen",
                detail=f"{_btc(returned)} se envían a direcciones que también aparecen como "
                "entrada en esta misma transacción.",
            )
        )
        interpretations.append(
            Finding(
                label="Importe nuevo estimado",
                detail=f"Descontando lo que vuelve a direcciones de origen, como máximo "
                f"{_btc(w.value_sat - returned)} salen hacia direcciones distintas "
                "de las de origen.",
                method="Resta de salidas que reutilizan una dirección de entrada.",
                confidence="alta",
            )
        )
    if w.unknown_address_output_count:
        unknowns.append(
            Finding(
                label="Salidas sin dirección estándar",
                detail=f"{w.unknown_address_output_count} salidas con valor usan scripts sin "
                "dirección estándar.",
            )
        )

    if w.input_count >= 5 and w.output_count <= 2:
        interpretations.append(
            Finding(
                label="Posible consolidación de fondos",
                detail="Muchas entradas se agrupan en una o dos salidas. Es un patrón habitual "
                "cuando un mismo operador reúne sus UTXO, pero no lo prueba.",
                method="Heurística: ≥5 entradas y ≤2 salidas.",
                confidence="media",
            )
        )
    if w.output_count >= 10:
        interpretations.append(
            Finding(
                label="Posible pago en lote",
                detail="Una transacción reparte fondos entre muchas salidas. Es un patrón "
                "habitual de pagos agrupados, pero no identifica a quien paga.",
                method="Heurística: ≥10 salidas.",
                confidence="media",
            )
        )
    if w.output_count == 2 and not returned:
        interpretations.append(
            Finding(
                label="Posible pago con cambio",
                detail="Con dos salidas, normalmente una es el pago y otra el cambio, "
                "pero no es posible saber con certeza cuál es cuál.",
                method="Heurística: exactamente 2 salidas.",
                confidence="baja",
            )
        )
    if w.output_count == 1 and w.input_count <= 2:
        interpretations.append(
            Finding(
                label="Movimiento íntegro a una sola salida",
                detail="Todo el valor (menos la comisión) va a una única salida, sin cambio. "
                "Puede ser un pago exacto o un traspaso entre direcciones del mismo titular.",
                method="Heurística: 1 salida, ≤2 entradas.",
                confidence="baja",
            )
        )

    return Analysis(observed=observed, interpretations=interpretations, unknowns=unknowns)
