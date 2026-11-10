import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// SVG presentation attributes can't read CSS variables, so chart colors are
// mirrored here from styles.css (--accent, --grid, --muted, --surface-2).
export const CHART = {
  accent: "#3d8bff",
  accentHover: "#7ab0ff",
  grid: "#1f2633",
  axis: "#7d879c",
  surface: "#121722",
};

type Row = Record<string, string | number | null>;

interface ChartProps {
  data: Row[];
  xKey: string;
  yKey: string;
  yLabel: string;
  xFormat?: (v: string | number) => string;
  yFormat?: (v: number) => string;
  height?: number;
  kind?: "bar" | "line";
}

function ChartTooltip({
  active,
  payload,
  label,
  xFormat,
  yFormat,
  yLabel,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string | number;
  xFormat: (v: string | number) => string;
  yFormat: (v: number) => string;
  yLabel: string;
}) {
  if (!active || !payload?.length || label === undefined) return null;
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{xFormat(label)}</div>
      <div>
        {yLabel}: <strong>{yFormat(payload[0].value)}</strong>
      </div>
    </div>
  );
}

/** Single-series chart with hover tooltip and an accessible table view. */
export function SeriesChart({
  data,
  xKey,
  yKey,
  yLabel,
  xFormat = (v) => String(v),
  yFormat = (v) => String(v),
  height = 220,
  kind = "bar",
}: ChartProps) {
  const [showTable, setShowTable] = useState(false);
  const common = {
    data,
    margin: { top: 8, right: 8, bottom: 0, left: 0 },
  };
  const axes = (
    <>
      <CartesianGrid vertical={false} stroke={CHART.grid} />
      <XAxis
        dataKey={xKey}
        tickFormatter={xFormat}
        stroke={CHART.axis}
        tickLine={false}
        axisLine={{ stroke: CHART.grid }}
        fontSize={11}
        minTickGap={24}
      />
      <YAxis
        tickFormatter={(v: number) => yFormat(v)}
        stroke={CHART.axis}
        tickLine={false}
        axisLine={false}
        fontSize={11}
        width={64}
      />
      <Tooltip
        cursor={kind === "bar" ? { fill: "rgba(61,139,255,0.08)" } : { stroke: CHART.axis, strokeDasharray: "3 3" }}
        content={<ChartTooltip xFormat={xFormat} yFormat={yFormat} yLabel={yLabel} />}
      />
    </>
  );

  return (
    <div>
      <div style={{ width: "100%", height }} role="img" aria-label={`Gráfico: ${yLabel}`}>
        <ResponsiveContainer>
          {kind === "bar" ? (
            <BarChart {...common} barCategoryGap={2}>
              {axes}
              <Bar dataKey={yKey} fill={CHART.accent} radius={[4, 4, 0, 0]} activeBar={{ fill: CHART.accentHover }} isAnimationActive={false} />
            </BarChart>
          ) : (
            <LineChart {...common}>
              {axes}
              <Line
                type="monotone"
                dataKey={yKey}
                stroke={CHART.accent}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: CHART.surface, strokeWidth: 2 }}
                isAnimationActive={false}
                connectNulls={false}
              />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
      <button className="btn btn-link" onClick={() => setShowTable((s) => !s)} aria-expanded={showTable}>
        {showTable ? "Ocultar tabla" : "Ver datos en tabla"}
      </button>
      {showTable && (
        <div className="table-wrap chart-table">
          <table>
            <thead>
              <tr>
                <th>{xKey}</th>
                <th className="num">{yLabel}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr key={i}>
                  <td>{xFormat(row[xKey] as string | number)}</td>
                  <td className="num">{row[yKey] === null ? "—" : yFormat(row[yKey] as number)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
