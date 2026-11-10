import { useState, type FormEvent } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { apiGet, describeError } from "../api/client";
import { useHealth } from "../api/hooks";
import type { SearchResult } from "../api/types";
import { classifyQuery } from "../lib/format";
import { MODULES } from "../modules";

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

export function SearchBox() {
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const query = q.trim();
    if (!query) return;
    if (classifyQuery(query) === "invalid") {
      setError("Introduce una altura de bloque, hash de bloque, txid o dirección mainnet.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await apiGet<SearchResult>(`/search?q=${encodeURIComponent(query)}`);
      const path = r.type === "block" ? `/block/${r.id}` : r.type === "transaction" ? `/tx/${r.id}` : `/address/${r.id}`;
      navigate(path);
      setQ("");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="search" onSubmit={onSubmit} role="search">
      <input
        aria-label="Buscar en la blockchain"
        placeholder="Buscar bloque, altura, txid o dirección…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setError(null);
        }}
        spellCheck={false}
      />
      <button className="btn" type="submit" disabled={busy}>
        {busy ? "Buscando…" : "Buscar"}
      </button>
      {error && (
        <div className="search-error" role="alert">
          {error}
        </div>
      )}
    </form>
  );
}

function HealthBadge() {
  const { data, isError } = useHealth();
  const state = isError ? "down" : data?.status === "ok" ? "ok" : data ? "degraded" : "unknown";
  const label = { ok: "Fuentes conectadas", degraded: "Servicio degradado", down: "Backend sin conexión", unknown: "Comprobando…" }[state];
  return (
    <NavLink to="/system" className={`health health-${state}`}>
      <span className="dot" aria-hidden />
      {label}
    </NavLink>
  );
}

export function Layout() {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <span className="brand-mark" aria-hidden>₿</span>
          <span>
            BITCOIN
            <br />
            INTELLIGENCE
          </span>
        </div>
        <nav aria-label="Módulos">
          {MODULES.map((m) =>
            m.path ? (
              <NavLink key={m.key} to={m.path} end={m.path === "/"} className="nav-item" onClick={() => setOpen(false)}>
                <Icon d={m.icon} />
                <span>{m.label}</span>
              </NavLink>
            ) : (
              <span key={m.key} className="nav-item disabled" aria-disabled="true" title={`Disponible en la Fase ${m.phase}`}>
                <Icon d={m.icon} />
                <span>{m.label}</span>
                <span className="phase">Fase {m.phase}</span>
              </span>
            ),
          )}
        </nav>
        <p className="sidebar-note">Solo datos públicos de la blockchain. Sin custodia, sin claves privadas, sin transacciones.</p>
      </aside>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      <div className="main">
        <header className="topbar">
          <button className="btn btn-ghost menu-btn" aria-label="Abrir menú" onClick={() => setOpen((o) => !o)}>
            ☰
          </button>
          <SearchBox key={location.pathname} />
          <HealthBadge />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
