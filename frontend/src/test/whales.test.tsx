import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes, makeQueryClient } from "../App";
import { whaleQuery } from "../api/hooks";

const SATS = 100_000_000;
const now = new Date().toISOString();
const tiers = [
  { level: 1, min_btc: 100, label: "Grande" },
  { level: 2, min_btc: 1000, label: "Muy grande" },
  { level: 3, min_btc: 10000, label: "Ballena" },
];
const tracking = {
  enabled: true,
  min_btc: 100,
  tiers,
  blocks_scanned: 144,
  lowest_height: 1,
  highest_height: 144,
  last_scan_at: now,
  coverage_since: new Date(Date.now() - 48 * 3_600_000).toISOString(),
  notes: ["El importe es la suma de todas las salidas e incluye el posible cambio."],
};
const whale = {
  txid: "a".repeat(64),
  value_sat: 2500 * SATS,
  fee_sat: 5000,
  vsize: 250,
  confirmed: true,
  block_height: 975000,
  block_hash: "b".repeat(64),
  block_time: now,
  first_seen_at: now,
  event_time: now,
  detected_via: "block",
  source: "mempool.space",
  tier: tiers[1],
  enriched: true,
  upstream_missing: false,
  input_count: 40,
  output_count: 1,
  returned_to_input_sat: 0,
};
const health = {
  status: "ok",
  version: "0.2.0",
  environment: "test",
  time: now,
  database: { ok: true, backend: "sqlite" },
  cache: { entries: 0, hits: 0, misses: 0 },
  providers: [],
  ingestion: { enabled: false, running: false, interval_s: null, last_run_at: null, last_status: null, stored_blocks: 0 },
};
const stats = {
  hours: 24,
  count: 1,
  confirmed_count: 1,
  unconfirmed_count: 0,
  volume_sat: whale.value_sat,
  largest: whale,
  by_hour: [{ hour: now, count: 1, volume_sat: whale.value_sat }],
  by_tier: tiers.map((t) => ({ tier: t, count: t.level === 2 ? 1 : 0, volume_sat: 0 })),
  generated_at: now,
  source: "database",
  tracking,
};
const emptyList = { data: [], total: 0, limit: 25, offset: 0, generated_at: now, source: "database", tracking };

type Handler = (url: string, init?: RequestInit) => { status: number; body?: unknown };
let calls: { url: string; init?: RequestInit }[] = [];

function stub(handler: Handler) {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, init });
      const r = url.startsWith("/api/v1/health") ? { status: 200, body: health } : handler(url, init);
      return new Response(r.body === undefined ? null : JSON.stringify(r.body), {
        status: r.status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() =>
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  ),
);
afterEach(() => vi.unstubAllGlobals());

describe("whaleQuery", () => {
  it("builds query strings with UTC day bounds and omits defaults", () => {
    const q = whaleQuery({ min_btc: "500", since: "2026-11-01", until: "2026-11-02", status: "all", sort: "time" });
    expect(q).toBe("min_btc=500&since=2026-11-01T00%3A00%3A00Z&until=2026-11-02T23%3A59%3A59Z&limit=25");
    expect(whaleQuery({ status: "unconfirmed", sort: "value", offset: 25 })).toBe(
      "status=unconfirmed&sort=value&limit=25&offset=25",
    );
  });
});

describe("Whale Tracker page", () => {
  it("lists movements with tier/structure and sends filters to the API", async () => {
    stub((url) => {
      if (url.startsWith("/api/v1/whales/stats")) return { status: 200, body: stats };
      if (url.startsWith("/api/v1/whales")) return { status: 200, body: { ...emptyList, data: [whale], total: 1 } };
      return { status: 404, body: { error: { code: "not_found", message: "nf" } } };
    });
    renderAt("/whales");
    expect(await screen.findByText("40 → 1")).toBeInTheDocument();
    expect(screen.getAllByText("Muy grande").length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("Mín. BTC"), { target: { value: "1000" } });
    fireEvent.change(screen.getByLabelText("Estado"), { target: { value: "confirmed" } });
    fireEvent.click(screen.getByText("Aplicar"));
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("min_btc=1000") && c.url.includes("status=confirmed"))).toBe(true),
    );
  });

  it("validates filters client-side", async () => {
    stub((url) => (url.startsWith("/api/v1/whales/stats") ? { status: 200, body: stats } : { status: 200, body: emptyList }));
    renderAt("/whales");
    await screen.findByText("Ningún movimiento coincide con los filtros.");
    fireEvent.change(screen.getByLabelText("Mín. BTC"), { target: { value: "500" } });
    fireEvent.change(screen.getByLabelText("Máx. BTC"), { target: { value: "100" } });
    fireEvent.click(screen.getByText("Aplicar"));
    expect(await screen.findByText("El máximo debe ser mayor que el mínimo.")).toBeInTheDocument();
  });

  it("detail separates observed, interpretation and unknown layers", async () => {
    stub((url) => {
      if (url.startsWith("/api/v1/whales/")) {
        return {
          status: 200,
          body: {
            whale,
            generated_at: now,
            enrichment_error: null,
            analysis: {
              observed: [{ label: "Importe total de salidas", detail: "2500 BTC", method: null, confidence: null }],
              interpretations: [
                { label: "Posible consolidación de fondos", detail: "x", method: "Heurística", confidence: "media" },
              ],
              unknowns: [{ label: "Identidad de los propietarios", detail: "y", method: null, confidence: null }],
            },
          },
        };
      }
      return { status: 503, body: { error: { code: "upstream_unavailable", message: "down" } } };
    });
    renderAt(`/whales/${whale.txid}`);
    expect(await screen.findByText("Posible consolidación de fondos")).toBeInTheDocument();
    expect(screen.getByText("confianza media")).toBeInTheDocument();
    expect(screen.getByText("Identidad de los propietarios")).toBeInTheDocument();
    expect(screen.getByText("Observado")).toBeInTheDocument();
  });
});

describe("Alerts page", () => {
  it("validates the minimum threshold and creates a rule with a POST", async () => {
    stub((url, init) => {
      if (url.startsWith("/api/v1/alerts/rules") && init?.method === "POST") {
        return {
          status: 201,
          body: { id: 1, name: "Grandes", min_btc: 1000, include_unconfirmed: true, enabled: true, created_at: now, updated_at: now, events_count: 0 },
        };
      }
      if (url.startsWith("/api/v1/alerts/rules")) return { status: 200, body: [] };
      if (url.startsWith("/api/v1/alerts/events")) return { status: 200, body: { data: [], total: 0, generated_at: now, source: "database" } };
      if (url.startsWith("/api/v1/whales/stats")) return { status: 200, body: stats };
      return { status: 404, body: {} };
    });
    renderAt("/alerts");
    await screen.findByText("No hay reglas. Crea la primera con el formulario.");

    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Grandes" } });
    fireEvent.change(screen.getByLabelText("Umbral (BTC)"), { target: { value: "50" } });
    fireEvent.click(screen.getByText("Crear regla"));
    expect(await screen.findByText(/El umbral mínimo es 100 BTC/)).toBeInTheDocument();
    expect(calls.some((c) => c.init?.method === "POST")).toBe(false);

    fireEvent.change(screen.getByLabelText("Umbral (BTC)"), { target: { value: "1000" } });
    fireEvent.click(screen.getByText("Crear regla"));
    await waitFor(() => {
      const post = calls.find((c) => c.init?.method === "POST");
      expect(post).toBeDefined();
      expect(JSON.parse(String(post!.init!.body))).toEqual({
        name: "Grandes",
        min_btc: 1000,
        include_unconfirmed: true,
        enabled: true,
      });
    });
  });
});
