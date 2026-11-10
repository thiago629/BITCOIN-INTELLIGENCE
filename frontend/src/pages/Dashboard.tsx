import { useMemo } from "react";
import { useBlockHistory, useNetworkHistory, useNetworkSummary, useRecentBlocks } from "../api/hooks";
import { SeriesChart } from "../components/Charts";
import { BlocksTable } from "../components/BlocksTable";
import { Empty, ErrorState, Freshness, Loading, PageHeader, Panel, Stat, StoredFreshness } from "../components/ui";
import {
  formatBTC,
  formatFeeRate,
  formatInt,
  formatNumber,
  formatTime,
  formatVBytes,
  satsToBTC,
  timeAgo,
} from "../lib/format";
import { bandMempool } from "../lib/mempool";
import { useNow } from "../lib/useNow";

function NetworkOverview() {
  const { data, isLoading, error, refetch } = useNetworkSummary();
  const now = useNow(10_000);
  if (isLoading) return <Panel title="Estado de la red"><Loading /></Panel>;
  if (error || !data) return <Panel title="Estado de la red"><ErrorState error={error} onRetry={() => refetch()} /></Panel>;

  const { tip_height, mempool, fees, difficulty } = data;
  const unavailable = (msg: string | null) => <span className="muted small" title={msg ?? ""}>No disponible</span>;

  return (
    <div className="grid grid-4">
      <Panel title="Altura de bloque" meta={<Freshness meta={tip_height.meta} />}>
        {tip_height.data !== null ? <Stat label="Último bloque" value={formatInt(tip_height.data)} /> : unavailable(tip_height.error)}
      </Panel>
      <Panel title="Comisiones recomendadas" meta={<Freshness meta={fees.meta} />}>
        {fees.data ? (
          <div className="fee-grid">
            <Stat label="Prioritaria" value={formatFeeRate(fees.data.fastest)} />
            <Stat label="~30 min" value={formatFeeRate(fees.data.half_hour)} />
            <Stat label="~1 hora" value={formatFeeRate(fees.data.hour)} />
            <Stat label="Económica" value={formatFeeRate(fees.data.economy)} />
          </div>
        ) : (
          unavailable(fees.error)
        )}
        {fees.data?.method === "target_estimates" && (
          <p className="muted small">Derivadas de estimaciones por objetivo de confirmación.</p>
        )}
      </Panel>
      <Panel title="Mempool" meta={<Freshness meta={mempool.meta} />}>
        {mempool.data ? (
          <div className="fee-grid">
            <Stat label="Tx pendientes" value={formatInt(mempool.data.count)} />
            <Stat label="Tamaño" value={formatVBytes(mempool.data.vsize)} />
            <Stat label="Comisiones totales" value={formatBTC(mempool.data.total_fee_sat, 4)} />
            <Stat label="Bloques para vaciar" value={`≈ ${formatNumber(mempool.data.vsize / 1_000_000, 0)}`} hint="a 1 MvB por bloque" />
          </div>
        ) : (
          unavailable(mempool.error)
        )}
      </Panel>
      <Panel title="Ajuste de dificultad" meta={<Freshness meta={difficulty.meta} />}>
        {difficulty.data ? (
          <>
            <Stat
              label="Cambio estimado"
              value={
                <span className={difficulty.data.difficulty_change_percent >= 0 ? "pos" : "neg"}>
                  {difficulty.data.difficulty_change_percent >= 0 ? "+" : ""}
                  {formatNumber(difficulty.data.difficulty_change_percent, 2)} %
                </span>
              }
              hint={`Bloque ${formatInt(difficulty.data.next_retarget_height)} · ${timeAgo(difficulty.data.estimated_retarget_date, now)}`}
            />
            <div className="progress" aria-label="Progreso del periodo de dificultad">
              <div style={{ width: `${Math.min(100, difficulty.data.progress_percent)}%` }} />
            </div>
            <p className="muted small">
              {formatNumber(difficulty.data.progress_percent, 1)} % del periodo · faltan {formatInt(difficulty.data.remaining_blocks)} bloques
            </p>
          </>
        ) : (
          unavailable(difficulty.error)
        )}
      </Panel>
    </div>
  );
}

function MempoolDistribution() {
  const { data } = useNetworkSummary();
  const mempool = data?.mempool;
  const bands = useMemo(() => (mempool?.data ? bandMempool(mempool.data.fee_histogram) : []), [mempool?.data]);
  return (
    <Panel
      title="Mempool por tasa de comisión"
      subtitle="Volumen pendiente (MvB) agrupado por sat/vB"
      meta={<Freshness meta={mempool?.meta} />}
    >
      {!mempool ? <Loading /> : mempool.data ? (
        <SeriesChart data={bands} xKey="band" yKey="mvb" yLabel="MvB" xFormat={(v) => `${v} sat/vB`} yFormat={(v) => formatNumber(v, 2)} />
      ) : (
        <Empty>Datos de mempool no disponibles.</Empty>
      )}
    </Panel>
  );
}

function BlockHistoryCharts() {
  const { data, isLoading, error, refetch } = useBlockHistory(144);
  const rows = useMemo(
    () =>
      (data?.data ?? [])
        .slice()
        .reverse()
        .map((b) => ({
          height: b.height,
          tx_count: b.tx_count,
          fees_btc: b.total_fees_sat === null ? null : satsToBTC(b.total_fees_sat),
        })),
    [data],
  );
  const hasFees = rows.some((r) => r.fees_btc !== null);
  const meta = <StoredFreshness generatedAt={data?.meta.generated_at} records={data?.meta.records} />;

  const body = (render: () => JSX.Element) =>
    isLoading ? <Loading /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : rows.length === 0 ? (
      <Empty>
        Aún no hay historial almacenado. El proceso de ingesta lo guarda automáticamente; aparecerá en el próximo ciclo.
      </Empty>
    ) : (
      render()
    );

  return (
    <div className="grid grid-2">
      <Panel title="Transacciones por bloque" subtitle={`Últimos ${rows.length} bloques almacenados`} meta={meta}>
        {body(() => (
          <SeriesChart data={rows} xKey="height" yKey="tx_count" yLabel="Transacciones" xFormat={(v) => `#${v}`} yFormat={(v) => formatInt(v)} />
        ))}
      </Panel>
      <Panel title="Comisiones totales por bloque" subtitle="BTC pagados a mineros en comisiones" meta={meta}>
        {body(() =>
          hasFees ? (
            <SeriesChart data={rows} xKey="height" yKey="fees_btc" yLabel="Comisiones (BTC)" xFormat={(v) => `#${v}`} yFormat={(v) => formatNumber(v, 4)} />
          ) : (
            <Empty>La fuente activa no proporciona comisiones por bloque.</Empty>
          ),
        )}
      </Panel>
    </div>
  );
}

function FeeTimeline() {
  const { data, isLoading, error, refetch } = useNetworkHistory(24);
  const rows = (data?.data ?? []).map((s) => ({ t: s.captured_at, fee: s.fee_fastest }));
  return (
    <Panel
      title="Comisión prioritaria — últimas 24 h"
      subtitle="Instantáneas guardadas por el proceso de ingesta"
      meta={<StoredFreshness generatedAt={data?.meta.generated_at} records={data?.meta.records} />}
    >
      {isLoading ? <Loading /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : rows.length < 2 ? (
        <Empty>Se necesitan al menos dos instantáneas. Se registran una por ciclo de ingesta.</Empty>
      ) : (
        <SeriesChart
          kind="line"
          data={rows}
          xKey="t"
          yKey="fee"
          yLabel="sat/vB"
          xFormat={(v) => (typeof v === "string" && v.includes("T") ? formatTime(v) : String(v))}
          yFormat={(v) => formatNumber(v, 1)}
        />
      )}
    </Panel>
  );
}

function LatestBlocks() {
  const { data, isLoading, error, refetch } = useRecentBlocks();
  return (
    <Panel title="Últimos bloques" meta={<Freshness meta={data?.meta} />}>
      {isLoading ? <Loading /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : (
        <BlocksTable blocks={(data?.data ?? []).slice(0, 8)} compact />
      )}
    </Panel>
  );
}

export function Dashboard() {
  return (
    <>
      <PageHeader title="Dashboard">Visión general de la red Bitcoin con datos públicos. Cada panel indica su fuente y cuándo se actualizó.</PageHeader>
      <NetworkOverview />
      <div className="grid grid-2">
        <LatestBlocks />
        <MempoolDistribution />
      </div>
      <BlockHistoryCharts />
      <FeeTimeline />
    </>
  );
}
