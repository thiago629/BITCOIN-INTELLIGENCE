import { useMemo, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTransaction, useWhaleDetail, useWhales, useWhaleStats, type WhaleFilters } from "../api/hooks";
import type { Finding, Tracking, Whale } from "../api/types";
import { SeriesChart } from "../components/Charts";
import { Empty, ErrorState, HashLink, KeyValue, Loading, PageHeader, Panel, Stat, StoredFreshness } from "../components/ui";
import { formatBTC, formatDateTime, formatFeeRate, formatInt, formatTime, shortHash, timeAgo, formatNumber } from "../lib/format";
import { useNow } from "../lib/useNow";

export function TierBadge({ whale }: { whale: Whale }) {
  if (!whale.tier) return null;
  return <span className={`tier tier-${whale.tier.level}`}>{whale.tier.label}</span>;
}

export function StatusBadge({ whale }: { whale: Whale }) {
  if (whale.confirmed) return <span className="status status-ok">Confirmada</span>;
  if (whale.upstream_missing) return <span className="status status-degraded">No localizada</span>;
  return <span className="status status-warn">Mempool</span>;
}

function TrackingNotes({ tracking }: { tracking: Tracking }) {
  return (
    <div className="notes">
      <p>
        Se registran transacciones con salidas totales ≥ <strong>{formatInt(tracking.min_btc)} BTC</strong>. Bloques analizados:{" "}
        <strong>{formatInt(tracking.blocks_scanned)}</strong>
        {tracking.lowest_height !== null && tracking.highest_height !== null && (
          <> (#{formatInt(tracking.lowest_height)} – #{formatInt(tracking.highest_height)})</>
        )}
        {tracking.last_scan_at && <> · último análisis {formatDateTime(tracking.last_scan_at)}</>}.
        {!tracking.enabled && <strong> El rastreo está desactivado en este servidor.</strong>}
      </p>
      <ul>
        {tracking.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </div>
  );
}

const STATUS_OPTIONS = [
  ["all", "Todas"],
  ["confirmed", "Confirmadas"],
  ["unconfirmed", "Sin confirmar"],
] as const;

function filtersFrom(params: URLSearchParams): WhaleFilters {
  return {
    min_btc: params.get("min") ?? "",
    max_btc: params.get("max") ?? "",
    since: params.get("since") ?? "",
    until: params.get("until") ?? "",
    status: (params.get("status") as WhaleFilters["status"]) ?? "all",
    sort: (params.get("sort") as WhaleFilters["sort"]) ?? "time",
    offset: Number(params.get("offset") ?? 0) || 0,
  };
}

function FilterBar({ value, onApply }: { value: WhaleFilters; onApply: (f: WhaleFilters) => void }) {
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof WhaleFilters) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [k]: e.target.value }));

  function submit(e: FormEvent) {
    e.preventDefault();
    const min = draft.min_btc ? Number(draft.min_btc) : undefined;
    const max = draft.max_btc ? Number(draft.max_btc) : undefined;
    if ((min !== undefined && (Number.isNaN(min) || min < 0)) || (max !== undefined && (Number.isNaN(max) || max <= 0))) {
      setError("Los importes deben ser números positivos.");
      return;
    }
    if (min !== undefined && max !== undefined && max <= min) {
      setError("El máximo debe ser mayor que el mínimo.");
      return;
    }
    if (draft.since && draft.until && draft.until < draft.since) {
      setError("La fecha final debe ser posterior a la inicial.");
      return;
    }
    setError(null);
    onApply({ ...draft, offset: 0 });
  }

  function reset() {
    const empty: WhaleFilters = { min_btc: "", max_btc: "", since: "", until: "", status: "all", sort: "time", offset: 0 };
    setDraft(empty);
    setError(null);
    onApply(empty);
  }

  return (
    <form className="filters" onSubmit={submit} aria-label="Filtros">
      <label>
        Mín. BTC
        <input inputMode="decimal" value={draft.min_btc} onChange={set("min_btc")} placeholder="100" />
      </label>
      <label>
        Máx. BTC
        <input inputMode="decimal" value={draft.max_btc} onChange={set("max_btc")} placeholder="—" />
      </label>
      <label>
        Desde (UTC)
        <input type="date" value={draft.since} onChange={set("since")} />
      </label>
      <label>
        Hasta (UTC)
        <input type="date" value={draft.until} onChange={set("until")} />
      </label>
      <label>
        Estado
        <select value={draft.status} onChange={set("status")}>
          {STATUS_OPTIONS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <label>
        Orden
        <select value={draft.sort} onChange={set("sort")}>
          <option value="time">Más recientes</option>
          <option value="value">Mayor importe</option>
        </select>
      </label>
      <div className="filters-actions">
        <button className="btn" type="submit">
          Aplicar
        </button>
        <button className="btn btn-ghost" type="button" onClick={reset}>
          Limpiar
        </button>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

export function WhaleTable({ whales, compact = false }: { whales: Whale[]; compact?: boolean }) {
  const now = useNow(15_000);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Transacción</th>
            <th className="num">Importe (salidas)</th>
            <th>Nivel</th>
            <th>Estado</th>
            <th>Cuándo</th>
            {!compact && <th className="num hide-sm">Estructura</th>}
            {!compact && <th className="num hide-sm">Tasa</th>}
          </tr>
        </thead>
        <tbody>
          {whales.map((w) => (
            <tr key={w.txid}>
              <td>
                <HashLink to={`/whales/${w.txid}`} hash={w.txid} />
              </td>
              <td className="num strong">{formatBTC(w.value_sat, 2)}</td>
              <td>
                <TierBadge whale={w} />
              </td>
              <td>
                <StatusBadge whale={w} />
              </td>
              <td title={formatDateTime(w.event_time)}>{timeAgo(w.event_time, now)}</td>
              {!compact && (
                <td className="num hide-sm muted">
                  {w.input_count !== null && w.output_count !== null ? `${w.input_count} → ${w.output_count}` : "—"}
                </td>
              )}
              {!compact && (
                <td className="num hide-sm">{w.fee_sat !== null && w.vsize ? formatFeeRate(w.fee_sat / w.vsize) : "—"}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatsRow() {
  const { data, isLoading, error, refetch } = useWhaleStats(24);
  const chart = useMemo(
    () => (data?.by_hour ?? []).map((b) => ({ hour: b.hour, count: b.count })),
    [data],
  );
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorState error={error} onRetry={() => refetch()} />;
  const coverage = data.tracking.coverage_since;
  const partial = !coverage || Date.parse(coverage) > Date.now() - data.hours * 3_600_000;
  return (
    <>
      {partial && data.tracking.blocks_scanned > 0 && (
        <div className="notice" role="status">
          Análisis inicial en curso: las cifras de 24 h solo incluyen bloques desde {formatDateTime(coverage)}. Se completan
          automáticamente en los próximos minutos.
        </div>
      )}
      <div className="grid grid-4">
        <Panel title="Movimientos (24 h)">
          <Stat label="Detectados" value={formatInt(data.count)} hint={`${formatInt(data.confirmed_count)} confirmados · ${formatInt(data.unconfirmed_count)} en mempool`} />
        </Panel>
        <Panel title="Volumen bruto (24 h)">
          <Stat label="Suma de salidas" value={formatBTC(data.volume_sat, 0)} hint="Incluye cambio: es un máximo" />
        </Panel>
        <Panel title="Mayor movimiento (24 h)">
          {data.largest ? (
            <Stat
              label={data.largest.tier?.label ?? "—"}
              value={<Link className="link" to={`/whales/${data.largest.txid}`}>{formatBTC(data.largest.value_sat, 2)}</Link>}
              hint={shortHash(data.largest.txid)}
            />
          ) : (
            <Stat label="Sin datos" value="—" />
          )}
        </Panel>
        <Panel title="Por nivel (24 h)">
          <div className="tier-list">
            {data.by_tier.map((t) => (
              <div key={t.tier.level}>
                <span className={`tier tier-${t.tier.level}`}>{t.tier.label}</span>
                <span className="muted small">≥ {formatInt(t.tier.min_btc)} BTC</span>
                <strong>{formatInt(t.count)}</strong>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <Panel
        title="Movimientos grandes por hora"
        subtitle={
          partial
            ? `Cobertura parcial: bloques analizados desde ${formatDateTime(data.tracking.coverage_since)}. Las horas anteriores aún no tienen datos (no significa cero).`
            : "Últimas 24 h, por hora del bloque (o de detección en mempool)"
        }
        meta={<StoredFreshness generatedAt={data.generated_at} records={data.count} />}
      >
        {data.tracking.blocks_scanned === 0 ? (
          <Empty>El análisis de bloques aún no ha empezado. Aparecerán datos en cuanto se escaneen los primeros bloques.</Empty>
        ) : (
          <SeriesChart data={chart} xKey="hour" yKey="count" yLabel="Movimientos" xFormat={(v) => formatTime(String(v))} yFormat={(v) => formatInt(v)} height={180} />
        )}
      </Panel>
    </>
  );
}

export function WhaleTrackerPage() {
  const [params, setParams] = useSearchParams();
  const filters = filtersFrom(params);
  const { data, isLoading, isFetching, error, refetch } = useWhales(filters);
  const limit = 25;

  function apply(f: WhaleFilters) {
    const p = new URLSearchParams();
    if (f.min_btc) p.set("min", f.min_btc);
    if (f.max_btc) p.set("max", f.max_btc);
    if (f.since) p.set("since", f.since);
    if (f.until) p.set("until", f.until);
    if (f.status && f.status !== "all") p.set("status", f.status);
    if (f.sort && f.sort !== "time") p.set("sort", f.sort);
    if (f.offset) p.set("offset", String(f.offset));
    setParams(p);
  }
  const offset = filters.offset ?? 0;

  return (
    <>
      <PageHeader title="Whale Tracker">
        Grandes movimientos de BTC detectados en bloques y en el mempool. Solo hechos observables: no se atribuyen identidades.
      </PageHeader>
      <StatsRow />
      <Panel
        title="Historial de movimientos"
        subtitle={data ? `${formatInt(data.total)} resultados` : undefined}
        meta={data && <StoredFreshness generatedAt={data.generated_at} records={data.total} />}
        actions={
          <div className="pager">
            <button className="btn btn-ghost" disabled={offset === 0} onClick={() => apply({ ...filters, offset: Math.max(0, offset - limit) })}>
              ←
            </button>
            <span className="muted small pager-label">
              {data && data.total > 0 ? `${offset + 1}–${Math.min(offset + limit, data.total)}` : "0"}
            </span>
            <button
              className="btn btn-ghost"
              disabled={!data || offset + limit >= data.total || isFetching}
              onClick={() => apply({ ...filters, offset: offset + limit })}
            >
              →
            </button>
          </div>
        }
      >
        <FilterBar key={params.toString()} value={filters} onApply={apply} />
        {isLoading ? (
          <Loading />
        ) : error || !data ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : data.data.length === 0 ? (
          <Empty>
            {data.tracking.blocks_scanned === 0
              ? "Todavía no se ha analizado ningún bloque."
              : "Ningún movimiento coincide con los filtros."}
          </Empty>
        ) : (
          <WhaleTable whales={data.data} />
        )}
        {data && <TrackingNotes tracking={data.tracking} />}
      </Panel>
    </>
  );
}

// ------------------------------------------------------------------ detail

function FindingList({ items, empty }: { items: Finding[]; empty: string }) {
  if (items.length === 0) return <p className="muted small">{empty}</p>;
  return (
    <ul className="findings">
      {items.map((f) => (
        <li key={f.label}>
          <div className="finding-label">
            {f.label}
            {f.confidence && <span className={`tag conf-${f.confidence}`}>confianza {f.confidence}</span>}
          </div>
          <div>{f.detail}</div>
          {f.method && <div className="muted small">Método: {f.method}</div>}
        </li>
      ))}
    </ul>
  );
}

interface FlowRow {
  address: string | null;
  value: number;
  count: number;
  isInputAddress: boolean;
}

function aggregate(items: { address: string | null; value_sat: number | null }[], inputs: Set<string>): FlowRow[] {
  const map = new Map<string, FlowRow>();
  for (const it of items) {
    const key = it.address ?? "∅";
    const row = map.get(key) ?? { address: it.address, value: 0, count: 0, isInputAddress: !!it.address && inputs.has(it.address) };
    row.value += it.value_sat ?? 0;
    row.count += 1;
    map.set(key, row);
  }
  return [...map.values()].sort((a, b) => b.value - a.value);
}

function FlowTable({ rows, total, kind }: { rows: FlowRow[]; total: number; kind: "in" | "out" }) {
  const shown = rows.slice(0, 15);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Dirección</th>
            <th className="num">{kind === "in" ? "Entradas" : "Salidas"}</th>
            <th className="num">Importe</th>
            <th className="num hide-sm">%</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.address ?? "none"}>
              <td>
                {r.address ? (
                  <Link className="link mono" to={`/address/${r.address}`} title={r.address}>
                    {shortHash(r.address, 10)}
                  </Link>
                ) : (
                  <span className="muted">sin dirección estándar</span>
                )}
                {kind === "out" && r.isInputAddress && <span className="tag tag-warn">vuelve a origen</span>}
              </td>
              <td className="num">{r.count}</td>
              <td className="num">{formatBTC(r.value)}</td>
              <td className="num hide-sm">{total ? formatNumber((r.value / total) * 100, 1) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > shown.length && (
        <p className="muted small table-note">
          Mostrando las 15 direcciones con mayor importe de {rows.length}. Detalle completo en la vista de transacción.
        </p>
      )}
    </div>
  );
}

function ObservableFlows({ txid }: { txid: string }) {
  const { data, isLoading, error, refetch } = useTransaction(txid);
  if (isLoading) return <Loading label="Cargando entradas y salidas…" />;
  if (error || !data) return <ErrorState error={error} onRetry={() => refetch()} />;
  const tx = data.data;
  const inputAddrs = new Set(tx.inputs.map((i) => i.address).filter((a): a is string => !!a));
  const ins = aggregate(tx.inputs, inputAddrs);
  const outs = aggregate(tx.outputs, inputAddrs);
  return (
    <div className="grid grid-2">
      <Panel title="Entradas observables" subtitle="Agrupadas por dirección">
        <FlowTable rows={ins} total={tx.total_input_sat ?? 0} kind="in" />
      </Panel>
      <Panel title="Salidas observables" subtitle="Agrupadas por dirección">
        <FlowTable rows={outs} total={tx.total_output_sat} kind="out" />
      </Panel>
    </div>
  );
}

export function WhaleDetailPage() {
  const { txid = "" } = useParams();
  const { data, isLoading, error, refetch } = useWhaleDetail(txid);
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorState error={error} onRetry={() => refetch()} />;
  const w = data.whale;
  const a = data.analysis;
  return (
    <>
      <PageHeader title={`Movimiento de ${formatBTC(w.value_sat, 2)}`}>
        <span className="mono break">{w.txid}</span>
        <div className="header-badges">
          <TierBadge whale={w} /> <StatusBadge whale={w} />
          <Link className="link small" to={`/tx/${w.txid}`}>
            Ver transacción completa →
          </Link>
        </div>
      </PageHeader>
      {data.enrichment_error && (
        <div className="state state-error" role="alert">
          No se pudo completar el análisis de la estructura ahora mismo. Se reintentará automáticamente.
        </div>
      )}
      <div className="grid grid-3">
        <Panel title="Observado" subtitle="Hechos leídos de la blockchain" className="layer layer-observed">
          <FindingList items={a.observed} empty="—" />
        </Panel>
        <Panel title="Interpretación" subtitle="Heurísticas, no hechos" className="layer layer-interp">
          <FindingList items={a.interpretations} empty="Ninguna heurística aplicable con los datos disponibles." />
        </Panel>
        <Panel title="Desconocido" subtitle="Lo que los datos no permiten saber" className="layer layer-unknown">
          <FindingList items={a.unknowns} empty="—" />
        </Panel>
      </div>
      <Panel title="Procedencia" meta={<StoredFreshness generatedAt={data.generated_at} records={1} />}>
        <KeyValue
          rows={[
            ["Detectado por", w.detected_via === "block" ? "Análisis de bloque completo" : "Muestra del mempool"],
            ["Fuente", w.source],
            ["Visto por primera vez", formatDateTime(w.first_seen_at)],
            ["Bloque", w.block_height !== null ? <Link className="link" to={`/block/${w.block_hash}`}>#{formatInt(w.block_height)}</Link> : "Pendiente"],
            ["Hora del bloque", formatDateTime(w.block_time)],
            ["Comisión", w.fee_sat !== null ? `${formatBTC(w.fee_sat)}${w.vsize ? ` · ${formatFeeRate(w.fee_sat / w.vsize)}` : ""}` : "—"],
          ]}
        />
      </Panel>
      {!w.upstream_missing && <ObservableFlows txid={w.txid} />}
    </>
  );
}

