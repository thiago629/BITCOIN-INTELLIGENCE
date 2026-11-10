import { useHealth, useIngestionRuns } from "../api/hooks";
import { Empty, ErrorState, KeyValue, Loading, PageHeader, Panel } from "../components/ui";
import { formatDateTime, formatInt, timeAgo } from "../lib/format";
import { useNow } from "../lib/useNow";

const STATUS_LABEL: Record<string, string> = { success: "Correcto", partial: "Parcial", failed: "Fallido" };

export function SystemPage() {
  const health = useHealth();
  const runs = useIngestionRuns();
  const now = useNow(5_000);

  return (
    <>
      <PageHeader title="Estado del sistema">Fuentes de datos, base de datos e ingesta. Se actualiza automáticamente.</PageHeader>
      {health.isLoading ? <Loading /> : health.error || !health.data ? (
        <ErrorState error={health.error} onRetry={() => health.refetch()} />
      ) : (
        <>
          <div className="grid grid-2">
            <Panel title="Servicio">
              <KeyValue
                rows={[
                  ["Estado", <span className={`status status-${health.data.status}`}>{health.data.status === "ok" ? "Operativo" : "Degradado"}</span>],
                  ["Versión", health.data.version],
                  ["Entorno", health.data.environment],
                  ["Base de datos", `${health.data.database.ok ? "Conectada" : "Error"} (${health.data.database.backend})`],
                  ["Caché", `${formatInt(health.data.cache.entries)} entradas · ${formatInt(health.data.cache.hits)} aciertos / ${formatInt(health.data.cache.misses)} fallos`],
                ]}
              />
            </Panel>
            <Panel title="Ingesta de datos">
              <KeyValue
                rows={[
                  ["Activa", health.data.ingestion.enabled ? (health.data.ingestion.running ? "Sí, en ejecución" : "Sí, detenida") : "Desactivada"],
                  ["Intervalo", health.data.ingestion.interval_s ? `${health.data.ingestion.interval_s} s` : "—"],
                  ["Último ciclo", health.data.ingestion.last_run_at ? timeAgo(health.data.ingestion.last_run_at, now) : "—"],
                  ["Resultado", health.data.ingestion.last_status ? STATUS_LABEL[health.data.ingestion.last_status] ?? health.data.ingestion.last_status : "—"],
                  ["Bloques almacenados", formatInt(health.data.ingestion.stored_blocks)],
                ]}
              />
            </Panel>
          </div>
          <Panel title="Proveedores de datos" subtitle="En orden de prioridad. Si uno falla, se usa el siguiente automáticamente.">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Proveedor</th>
                    <th>Estado</th>
                    <th className="num">Solicitudes</th>
                    <th className="num">Fallos</th>
                    <th className="hide-sm">Último éxito</th>
                    <th>Último error</th>
                  </tr>
                </thead>
                <tbody>
                  {health.data.providers.map((p) => (
                    <tr key={p.key}>
                      <td><strong>{p.name}</strong><div className="muted small">{p.capabilities.join(", ")}</div></td>
                      <td>
                        <span className={`status status-${p.in_cooldown ? "degraded" : p.healthy ? "ok" : "warn"}`}>
                          {p.in_cooldown ? `En pausa ${Math.ceil(p.cooldown_remaining_s)} s` : p.healthy ? "Operativo" : `${p.consecutive_failures} fallos seguidos`}
                        </span>
                      </td>
                      <td className="num">{formatInt(p.total_requests)}</td>
                      <td className="num">{formatInt(p.total_failures)}</td>
                      <td className="hide-sm">{p.last_success_at ? timeAgo(p.last_success_at, now) : "—"}</td>
                      <td className="muted small">{p.last_error ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
      <Panel title="Registro de ciclos de ingesta" subtitle="Últimos 20 ciclos (auditoría)">
        {runs.isLoading ? <Loading /> : runs.error ? <ErrorState error={runs.error} onRetry={() => runs.refetch()} /> : !runs.data?.length ? (
          <Empty>Todavía no se ha ejecutado ningún ciclo.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Inicio</th><th>Estado</th><th className="num">Bloques nuevos</th><th>Instantánea</th><th className="hide-sm">Fuentes</th><th>Error</th></tr>
              </thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.id}>
                    <td title={formatDateTime(r.started_at)}>{timeAgo(r.started_at, now)}</td>
                    <td><span className={`status status-${r.status === "success" ? "ok" : r.status === "partial" ? "warn" : "degraded"}`}>{STATUS_LABEL[r.status]}</span></td>
                    <td className="num">{formatInt(r.blocks_stored)}</td>
                    <td>{r.snapshot_stored ? "Sí" : "No"}</td>
                    <td className="hide-sm">{r.sources ?? "—"}</td>
                    <td className="muted small">{r.error ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
