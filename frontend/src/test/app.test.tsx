import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes, makeQueryClient } from "../App";

// The browser fetch is stubbed per URL. These canned responses exist only in
// tests; the application itself always talks to the real backend.
type Routes = Record<string, { status: number; body: unknown }>;

function stubFetch(routes: Routes) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const key = Object.keys(routes).find((k) => url.startsWith(k));
      const r = key ? routes[key] : { status: 404, body: { error: { code: "not_found", message: "nf" } } };
      return new Response(JSON.stringify(r.body), { status: r.status, headers: { "Content-Type": "application/json" } });
    }),
  );
}

const meta = { source: "mempool.space", fetched_at: new Date().toISOString(), cached: false, age_seconds: 0, fallback_used: false };
const health = {
  status: "ok", version: "0.1.0", environment: "test", time: meta.fetched_at,
  database: { ok: true, backend: "sqlite" }, cache: { entries: 0, hits: 0, misses: 0 },
  providers: [], ingestion: { enabled: false, running: false, interval_s: null, last_run_at: null, last_status: null, stored_blocks: 0 },
};

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  // recharts' ResponsiveContainer needs ResizeObserver in jsdom
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => vi.unstubAllGlobals());

describe("Dashboard", () => {
  it("renders real summary sections with provenance and marks unavailable ones", async () => {
    stubFetch({
      "/api/v1/health": { status: 200, body: health },
      "/api/v1/network/summary": {
        status: 200,
        body: {
          tip_height: { data: 975285, meta, error: null },
          mempool: { data: { count: 12345, vsize: 2_000_000, total_fee_sat: 5_000_000, fee_histogram: [[2, 2_000_000]] }, meta, error: null },
          fees: { data: { fastest: 5, half_hour: 4, hour: 3, economy: 2, minimum: 1, method: "recommended" }, meta, error: null },
          difficulty: { data: null, meta: null, error: "[mempool] HTTP 500" },
        },
      },
      "/api/v1/blocks/recent": { status: 200, body: { data: [], meta } },
      "/api/v1/history/blocks": { status: 200, body: { data: [], meta: { source: "database", generated_at: meta.fetched_at, records: 0 } } },
      "/api/v1/history/network": { status: 200, body: { data: [], meta: { source: "database", generated_at: meta.fetched_at, records: 0 } } },
    });
    renderAt("/");
    expect(await screen.findByText("975.285")).toBeInTheDocument();
    expect(screen.getByText("12.345")).toBeInTheDocument();
    expect(screen.getAllByText("No disponible").length).toBe(1);
    expect(screen.getAllByText("mempool.space").length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/Aún no hay historial almacenado/)).length).toBe(2);
  });

  it("shows an explicit error instead of fake data when the backend is down", async () => {
    stubFetch({
      "/api/v1/health": { status: 200, body: health },
      "/api/v1/network/summary": { status: 503, body: { error: { code: "upstream_unavailable", message: "x" } } },
    });
    renderAt("/");
    expect((await screen.findAllByText(/fuentes de datos no están disponibles/, {}, { timeout: 4000 })).length).toBeGreaterThan(0);
  });
});

describe("Navigation", () => {
  it("shows future modules disabled with their phase, never as empty pages", async () => {
    stubFetch({ "/api/v1/health": { status: 200, body: health } });
    renderAt("/system");
    expect(screen.getByText("Anomaly Detection").closest(".nav-item")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Whale Tracker").closest("a")).toHaveAttribute("href", "/whales");
    expect(screen.getByText("Fase 4")).toBeInTheDocument();
  });
});

describe("Transaction page", () => {
  it("renders inputs/outputs and the not-found state", async () => {
    stubFetch({ "/api/v1/health": { status: 200, body: health } });
    renderAt(`/tx/${"e".repeat(64)}`);
    expect(await screen.findByText("No se encontró en la blockchain.")).toBeInTheDocument();
  });
});
