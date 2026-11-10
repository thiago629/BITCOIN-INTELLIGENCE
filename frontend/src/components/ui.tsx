import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { describeError } from "../api/client";
import type { DataMeta } from "../api/types";
import { formatDateTime, shortHash, timeAgo } from "../lib/format";
import { useNow } from "../lib/useNow";

export function Panel({
  title,
  subtitle,
  meta,
  actions,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-head">
        <div>
          <h2 className="panel-title">{title}</h2>
          {subtitle && <p className="panel-sub">{subtitle}</p>}
        </div>
        {actions && <div className="panel-actions">{actions}</div>}
      </header>
      <div className="panel-body">{children}</div>
      {meta && <footer className="panel-foot">{meta}</footer>}
    </section>
  );
}

/** Provenance line: every piece of data says where it came from and when. */
export function Freshness({ meta }: { meta: DataMeta | null | undefined }) {
  const now = useNow(5_000);
  if (!meta) return null;
  return (
    <span className="freshness" title={`Obtenido: ${formatDateTime(meta.fetched_at)}`}>
      <span className="dot" aria-hidden />
      Fuente: <strong>{meta.source}</strong> · actualizado {timeAgo(meta.fetched_at, now)}
      {meta.cached && <span className="tag">caché</span>}
      {meta.fallback_used && <span className="tag tag-warn">proveedor de respaldo</span>}
    </span>
  );
}

export function StoredFreshness({ generatedAt, records }: { generatedAt?: string; records?: number }) {
  if (!generatedAt) return null;
  return (
    <span className="freshness">
      <span className="dot dot-db" aria-hidden />
      Fuente: <strong>base de datos de Bitcoin Intelligence</strong> · {records ?? 0} registros ·
      consultado {formatDateTime(generatedAt)}
    </span>
  );
}

export function Loading({ label = "Cargando datos…" }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <span>{describeError(error)}</span>
      {onRetry && (
        <button className="btn btn-ghost" onClick={onRetry}>
          Reintentar
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state state-empty">{children}</div>;
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function HashLink({ to, hash, size = 8 }: { to: string; hash: string; size?: number }) {
  return (
    <Link to={to} className="mono link" title={hash}>
      {shortHash(hash, size)}
    </Link>
  );
}

export function KeyValue({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([k, v]) => (
        <div className="kv-row" key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="page-header">
      <h1>{title}</h1>
      {children && <div className="page-header-sub">{children}</div>}
    </div>
  );
}
