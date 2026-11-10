import { useState, type FormEvent } from "react";
import { describeError } from "../api/client";
import { useAlertEvents, useAlertRules, useCreateRule, useDeleteRule, useUpdateRule, useWhaleStats } from "../api/hooks";
import type { AlertRule } from "../api/types";
import { Empty, ErrorState, HashLink, Loading, PageHeader, Panel, StoredFreshness } from "../components/ui";
import { formatBTC, formatDateTime, formatInt, timeAgo } from "../lib/format";
import { useNow } from "../lib/useNow";

function RuleForm({ minAllowed }: { minAllowed: number }) {
  const create = useCreateRule();
  const [name, setName] = useState("");
  const [minBtc, setMinBtc] = useState(String(Math.max(minAllowed, 500)));
  const [includeUnconfirmed, setIncludeUnconfirmed] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    const value = Number(minBtc.replace(",", "."));
    if (!name.trim()) return setError("Pon un nombre a la regla.");
    if (!Number.isFinite(value) || value <= 0) return setError("El umbral debe ser un número positivo.");
    if (value < minAllowed) return setError(`El umbral mínimo es ${formatInt(minAllowed)} BTC (por debajo no se rastrean transacciones).`);
    setError(null);
    create.mutate(
      { name: name.trim(), min_btc: value, include_unconfirmed: includeUnconfirmed, enabled: true },
      { onSuccess: () => setName("") },
    );
  }

  return (
    <form className="filters" onSubmit={submit} aria-label="Nueva regla de alerta">
      <label className="grow">
        Nombre
        <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="p. ej. Movimientos > 1.000 BTC" />
      </label>
      <label>
        Umbral (BTC)
        <input inputMode="decimal" value={minBtc} onChange={(e) => setMinBtc(e.target.value)} />
      </label>
      <label className="check">
        <input type="checkbox" checked={includeUnconfirmed} onChange={(e) => setIncludeUnconfirmed(e.target.checked)} />
        Incluir sin confirmar
      </label>
      <div className="filters-actions">
        <button className="btn" type="submit" disabled={create.isPending}>
          {create.isPending ? "Creando…" : "Crear regla"}
        </button>
      </div>
      {(error || create.error) && (
        <p className="form-error" role="alert">
          {error ?? describeError(create.error)}
        </p>
      )}
    </form>
  );
}

function RuleRow({ rule }: { rule: AlertRule }) {
  const update = useUpdateRule();
  const remove = useDeleteRule();
  const [confirming, setConfirming] = useState(false);
  const busy = update.isPending || remove.isPending;
  const err = update.error ?? remove.error;
  return (
    <tr>
      <td>
        <strong>{rule.name}</strong>
        {err && <div className="form-error small">{describeError(err)}</div>}
      </td>
      <td className="num">≥ {formatInt(rule.min_btc)} BTC</td>
      <td>{rule.include_unconfirmed ? "Mempool y bloques" : "Solo confirmadas"}</td>
      <td className="num">{formatInt(rule.events_count)}</td>
      <td>
        <label className="switch">
          <input
            type="checkbox"
            checked={rule.enabled}
            disabled={busy}
            onChange={(e) => update.mutate({ id: rule.id, enabled: e.target.checked })}
            aria-label={`Activar regla ${rule.name}`}
          />
          <span>{rule.enabled ? "Activa" : "Pausada"}</span>
        </label>
      </td>
      <td className="num">
        {confirming ? (
          <span className="confirm">
            <span className="small muted">¿Eliminar? Las alertas ya disparadas se conservan.</span>
            <button className="btn btn-danger" disabled={busy} onClick={() => remove.mutate(rule.id)}>
              Eliminar
            </button>
            <button className="btn btn-ghost" onClick={() => setConfirming(false)}>
              Cancelar
            </button>
          </span>
        ) : (
          <button className="btn btn-ghost" onClick={() => setConfirming(true)} disabled={busy}>
            Eliminar
          </button>
        )}
      </td>
    </tr>
  );
}

export function AlertsPage() {
  const rules = useAlertRules();
  const [offset, setOffset] = useState(0);
  const events = useAlertEvents(offset);
  const stats = useWhaleStats(24);
  const now = useNow(15_000);
  const minAllowed = stats.data?.tracking.min_btc ?? 100;

  return (
    <>
      <PageHeader title="Alerts">
        Reglas de alerta sobre grandes movimientos. Se evalúan automáticamente cada vez que el Whale Tracker detecta o confirma un movimiento.
      </PageHeader>
      <Panel title="Reglas" subtitle={`Umbral mínimo permitido: ${formatInt(minAllowed)} BTC`}>
        <RuleForm minAllowed={minAllowed} />
        {rules.isLoading ? (
          <Loading />
        ) : rules.error ? (
          <ErrorState error={rules.error} onRetry={() => rules.refetch()} />
        ) : !rules.data?.length ? (
          <Empty>No hay reglas. Crea la primera con el formulario.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Regla</th>
                  <th className="num">Umbral</th>
                  <th>Alcance</th>
                  <th className="num">Disparos</th>
                  <th>Estado</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rules.data.map((r) => (
                  <RuleRow key={r.id} rule={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel
        title="Alertas disparadas"
        subtitle={events.data ? `${formatInt(events.data.total)} en total` : undefined}
        meta={events.data && <StoredFreshness generatedAt={events.data.generated_at} records={events.data.total} />}
        actions={
          <div className="pager">
            <button className="btn btn-ghost" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - 25))}>
              ←
            </button>
            <button
              className="btn btn-ghost"
              disabled={!events.data || offset + 25 >= events.data.total}
              onClick={() => setOffset((o) => o + 25)}
            >
              →
            </button>
          </div>
        }
      >
        {events.isLoading ? (
          <Loading />
        ) : events.error ? (
          <ErrorState error={events.error} onRetry={() => events.refetch()} />
        ) : !events.data?.data.length ? (
          <Empty>Todavía no se ha disparado ninguna alerta. Solo se evalúan movimientos detectados después de crear la regla.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cuándo</th>
                  <th>Regla</th>
                  <th>Transacción</th>
                  <th className="num">Importe</th>
                  <th>Estado al disparar</th>
                </tr>
              </thead>
              <tbody>
                {events.data.data.map((e) => (
                  <tr key={e.id}>
                    <td title={formatDateTime(e.triggered_at)}>{timeAgo(e.triggered_at, now)}</td>
                    <td>
                      {e.rule_name}
                      <span className="muted small"> (≥ {formatInt(e.rule_min_btc)} BTC)</span>
                      {e.rule_id === null && <span className="tag">regla eliminada</span>}
                    </td>
                    <td>
                      <HashLink to={`/whales/${e.txid}`} hash={e.txid} />
                    </td>
                    <td className="num strong">{formatBTC(e.value_sat, 2)}</td>
                    <td>{e.confirmed ? <span className="status status-ok">Confirmada</span> : <span className="status status-warn">Mempool</span>}</td>
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
