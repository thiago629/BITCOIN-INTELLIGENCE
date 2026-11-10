import type { Block } from "../api/types";
import { formatBTC, formatBytes, formatFeeRate, formatInt, timeAgo } from "../lib/format";
import { useNow } from "../lib/useNow";
import { Empty, HashLink } from "./ui";
import { Link } from "react-router-dom";

export function BlocksTable({ blocks, compact = false }: { blocks: Block[]; compact?: boolean }) {
  const now = useNow(15_000);
  if (blocks.length === 0) return <Empty>No hay bloques.</Empty>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Altura</th>
            {!compact && <th>Hash</th>}
            <th>Hora</th>
            <th className="num">Tx</th>
            {!compact && <th className="num">Tamaño</th>}
            <th className="num">Comisiones</th>
            <th className="num hide-sm">Tasa mediana</th>
          </tr>
        </thead>
        <tbody>
          {blocks.map((b) => (
            <tr key={b.hash}>
              <td>
                <Link to={`/block/${b.hash}`} className="link mono">
                  {formatInt(b.height)}
                </Link>
              </td>
              {!compact && (
                <td>
                  <HashLink to={`/block/${b.hash}`} hash={b.hash} />
                </td>
              )}
              <td title={b.timestamp}>{timeAgo(b.timestamp, now)}</td>
              <td className="num">{formatInt(b.tx_count)}</td>
              {!compact && <td className="num">{formatBytes(b.size)}</td>}
              <td className="num">{formatBTC(b.total_fees_sat, 4)}</td>
              <td className="num hide-sm">{formatFeeRate(b.median_fee_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
