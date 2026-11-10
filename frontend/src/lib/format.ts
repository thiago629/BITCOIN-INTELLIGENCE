const SATS_PER_BTC = 100_000_000;

const nf = new Intl.NumberFormat("es-ES");

export function formatNumber(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("es-ES", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
}

export function formatInt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return nf.format(n);
}

/** Satoshis -> "1,23456789 BTC" (exact, never via float rounding of the sats). */
export function formatBTC(sats: number | null | undefined, maxDecimals = 8): string {
  if (sats === null || sats === undefined) return "—";
  const negative = sats < 0;
  const abs = Math.abs(sats);
  const whole = Math.floor(abs / SATS_PER_BTC);
  let frac = String(abs % SATS_PER_BTC).padStart(8, "0").slice(0, maxDecimals);
  frac = frac.replace(/0+$/, "");
  const body = `${nf.format(whole)}${frac ? "," + frac : ""}`;
  return `${negative ? "−" : ""}${body} BTC`;
}

export function satsToBTC(sats: number): number {
  return sats / SATS_PER_BTC;
}

export function formatFeeRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return "—";
  return `${formatNumber(rate, rate < 10 ? 2 : rate < 100 ? 1 : 0)} sat/vB`;
}

export function formatVBytes(vbytes: number | null | undefined): string {
  if (vbytes === null || vbytes === undefined) return "—";
  if (vbytes >= 1_000_000) return `${formatNumber(vbytes / 1_000_000, 2)} MvB`;
  if (vbytes >= 1_000) return `${formatNumber(vbytes / 1_000, 1)} kvB`;
  return `${formatInt(vbytes)} vB`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes >= 1_000_000) return `${formatNumber(bytes / 1_000_000, 2)} MB`;
  if (bytes >= 1_000) return `${formatNumber(bytes / 1_000, 1)} kB`;
  return `${formatInt(bytes)} B`;
}

export function shortHash(hash: string, size = 8): string {
  if (hash.length <= size * 2 + 1) return hash;
  return `${hash.slice(0, size)}…${hash.slice(-size)}`;
}

/** "hace 3 min" style relative time. `now` is injectable for tests. */
export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—";
  const diff = Math.round((now - new Date(iso).getTime()) / 1000);
  if (diff < 0) {
    const ahead = -diff;
    if (ahead < 3600) return `en ${Math.max(1, Math.round(ahead / 60))} min`;
    if (ahead < 86_400) return `en ${Math.round(ahead / 3600)} h`;
    return `en ${Math.round(ahead / 86_400)} días`;
  }
  if (diff < 5) return "ahora mismo";
  if (diff < 60) return `hace ${diff} s`;
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86_400) return `hace ${Math.floor(diff / 3600)} h`;
  return `hace ${Math.floor(diff / 86_400)} días`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(iso)) + " UTC";
}

export function formatTime(iso: string): string {
  return new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

export type QueryKind = "block" | "transaction" | "address" | "height" | "hex64" | "invalid";

/** Client-side pre-classification of the search box (server has final word). */
export function classifyQuery(raw: string): QueryKind {
  const q = raw.trim();
  if (/^\d{1,8}$/.test(q)) return "height";
  if (/^[0-9a-fA-F]{64}$/.test(q)) return "hex64";
  if (/^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$/.test(q)) return "address";
  if (/^(bc1|BC1)[02-9ac-hj-np-zAC-HJ-NP-Z]{11,87}$/.test(q)) return "address";
  return "invalid";
}
