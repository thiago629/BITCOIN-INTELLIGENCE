import { describe, expect, it } from "vitest";
import { classifyQuery, formatBTC, formatVBytes, shortHash, timeAgo } from "../lib/format";
import { bandMempool } from "../lib/mempool";

describe("formatBTC", () => {
  it("formats satoshis exactly without float drift", () => {
    expect(formatBTC(100_000_000)).toBe("1 BTC");
    expect(formatBTC(1)).toBe("0,00000001 BTC");
    expect(formatBTC(2_100_000_000_000_000)).toBe("21.000.000 BTC");
    expect(formatBTC(-150_000_000)).toBe("−1,5 BTC");
  });
  it("truncates to max decimals and shows unknown as dash", () => {
    expect(formatBTC(2_657_647, 4)).toBe("0,0265 BTC");
    expect(formatBTC(null)).toBe("—");
  });
});

describe("misc formatters", () => {
  it("formats vbytes", () => {
    expect(formatVBytes(38_465_468)).toBe("38,47 MvB");
    expect(formatVBytes(512)).toBe("512 vB");
  });
  it("shortens hashes", () => {
    expect(shortHash("a".repeat(64), 4)).toBe("aaaa…aaaa");
    expect(shortHash("abc")).toBe("abc");
  });
  it("relative time", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    expect(timeAgo("2026-01-01T11:58:00Z", now)).toBe("hace 2 min");
    expect(timeAgo("2026-01-01T12:00:02Z", now)).toBe("en 1 min");
    expect(timeAgo(null, now)).toBe("—");
  });
});

describe("classifyQuery", () => {
  it("detects query kinds", () => {
    expect(classifyQuery("840000")).toBe("height");
    expect(classifyQuery("f".repeat(64))).toBe("hex64");
    expect(classifyQuery("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")).toBe("address");
    expect(classifyQuery("bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq")).toBe("address");
    expect(classifyQuery("hello world")).toBe("invalid");
  });
});

describe("bandMempool", () => {
  it("groups histogram into fixed bands and preserves total", () => {
    const bands = bandMempool([
      [60, 1_000_000],
      [12, 2_000_000],
      [1.5, 3_000_000],
      [0.5, 500_000],
    ]);
    const byBand = Object.fromEntries(bands.map((b) => [b.band, b.mvb]));
    expect(byBand["≥50"]).toBe(1);
    expect(byBand["10–20"]).toBe(2);
    expect(byBand["1–2"]).toBe(3);
    expect(byBand["<1"]).toBe(0.5);
    expect(bands.reduce((s, b) => s + b.mvb, 0)).toBeCloseTo(6.5);
  });
});
