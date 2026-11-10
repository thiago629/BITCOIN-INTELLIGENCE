/** Fixed fee-rate bands (sat/vB) used to summarise the mempool histogram. */
export const FEE_BANDS: { label: string; min: number; max: number }[] = [
  { label: "<1", min: 0, max: 1 },
  { label: "1–2", min: 1, max: 2 },
  { label: "2–3", min: 2, max: 3 },
  { label: "3–5", min: 3, max: 5 },
  { label: "5–10", min: 5, max: 10 },
  { label: "10–20", min: 10, max: 20 },
  { label: "20–50", min: 20, max: 50 },
  { label: "≥50", min: 50, max: Infinity },
];

/**
 * Aggregate the provider's [feeRate, vsize] histogram into fixed bands.
 * Returns vsize per band in MvB. Total vsize is preserved exactly.
 */
export function bandMempool(histogram: [number, number][]): { band: string; mvb: number }[] {
  const totals = FEE_BANDS.map(() => 0);
  for (const [rate, vsize] of histogram) {
    const idx = FEE_BANDS.findIndex((b) => rate >= b.min && rate < b.max);
    totals[idx === -1 ? 0 : idx] += vsize;
  }
  return FEE_BANDS.map((b, i) => ({ band: b.label, mvb: Math.round((totals[i] / 1_000_000) * 100) / 100 }));
}
