import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAddress, useAddressTxs, useBlock, useBlockTxs, useRecentBlocks, useTransaction } from "../api/hooks";
import type { Transaction } from "../api/types";
import { BlocksTable } from "../components/BlocksTable";
import { SearchBox } from "../components/Layout";
import { Empty, ErrorState, Freshness, HashLink, KeyValue, Loading, PageHeader, Panel, Stat } from "../components/ui";
import {
  formatBTC,
  formatBytes,
  formatDateTime,
  formatFeeRate,
  formatInt,
  formatNumber,
  formatVBytes,
  shortHash,
} from "../lib/format";

export function ExplorerHome() {
  const [cursor, setCursor] = useState<number[]>([]); // stack of start heights
  const start = cursor[cursor.length - 1];
  const { data, isLoading, isFetching, error, refetch } = useRecentBlocks(start);
  const blocks = data?.data ?? [];
  const lowest = blocks.length ? blocks[blocks.length - 1].height : undefined;

  return (
    <>
      <PageHeader title="Blockchain Explorer">Consulta bloques, transacciones y direcciones públicas de Bitcoin.</PageHeader>
      <div className="explorer-search">
        <SearchBox />
      </div>
      <Panel
        title={start === undefined ? "Bloques recientes" : `Bloques desde #${formatInt(start)}`}
        meta={<Freshness meta={data?.meta} />}
        actions={
          <div className="pager">
            <button className="btn btn-ghost" disabled={cursor.length === 0} onClick={() => setCursor((c) => c.slice(0, -1))}>
              ← Más recientes
            </button>
            <button
              className="btn btn-ghost"
              disabled={lowest === undefined || lowest === 0 || isFetching}
              onClick={() => lowest !== undefined && setCursor((c) => [...c, lowest - 1])}
            >
              Anteriores →
            </button>
          </div>
        }
      >
        {isLoading ? <Loading /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : <BlocksTable blocks={blocks} />}
      </Panel>
    </>
  );
}

function TxRow({ tx }: { tx: Transaction }) {
  const coinbase = tx.inputs.some((i) => i.is_coinbase);
  return (
    <tr>
      <td>
        <HashLink to={`/tx/${tx.txid}`} hash={tx.txid} />
        {coinbase && <span className="tag">coinbase</span>}
      </td>
      <td className="num">{tx.inputs.length}</td>
      <td className="num">{tx.outputs.length}</td>
      <td className="num">{formatBTC(tx.total_output_sat)}</td>
      <td className="num hide-sm">{coinbase ? "—" : formatFeeRate(tx.fee_rate)}</td>
    </tr>
  );
}

export function BlockPage() {
  const { hash = "" } = useParams();
  const block = useBlock(hash);
  const [startIndex, setStartIndex] = useState(0);
  const txs = useBlockTxs(hash, startIndex);

  if (block.isLoading) return <Loading />;
  if (block.error || !block.data) return <ErrorState error={block.error} onRetry={() => block.refetch()} />;
  const b = block.data.data;
  const total = b.tx_count;

  return (
    <>
      <PageHeader title={`Bloque #${formatInt(b.height)}`}>
        <span className="mono break">{b.hash}</span>
      </PageHeader>
      <div className="grid grid-4">
        <Panel title="Transacciones"><Stat label="Total" value={formatInt(b.tx_count)} /></Panel>
        <Panel title="Comisiones"><Stat label="Total" value={formatBTC(b.total_fees_sat)} hint={b.total_fees_sat === null ? "No proporcionado por la fuente" : undefined} /></Panel>
        <Panel title="Tamaño"><Stat label="Bytes / peso" value={formatBytes(b.size)} hint={`${formatInt(b.weight)} WU`} /></Panel>
        <Panel title="Tasa mediana"><Stat label="Comisión" value={formatFeeRate(b.median_fee_rate)} /></Panel>
      </div>
      <Panel title="Detalles del bloque" meta={<Freshness meta={block.data.meta} />}>
        <KeyValue
          rows={[
            ["Hora (minero)", formatDateTime(b.timestamp)],
            ["Median time past", formatDateTime(b.median_time)],
            ["Bloque anterior", b.previous_block_hash ? <HashLink to={`/block/${b.previous_block_hash}`} hash={b.previous_block_hash} size={12} /> : "—"],
            ["Merkle root", <span className="mono break">{b.merkle_root ?? "—"}</span>],
            ["Dificultad", formatNumber(b.difficulty, 0)],
            ["Recompensa total", formatBTC(b.reward_sat)],
            ["Versión / nonce / bits", `${b.version ?? "—"} / ${b.nonce ?? "—"} / ${b.bits ?? "—"}`],
          ]}
        />
      </Panel>
      <Panel
        title="Transacciones del bloque"
        subtitle={`${formatInt(startIndex + 1)}–${formatInt(Math.min(startIndex + 25, total))} de ${formatInt(total)}`}
        meta={<Freshness meta={txs.data?.meta} />}
        actions={
          <div className="pager">
            <button className="btn btn-ghost" disabled={startIndex === 0} onClick={() => setStartIndex((s) => Math.max(0, s - 25))}>←</button>
            <button className="btn btn-ghost" disabled={startIndex + 25 >= total || txs.isFetching} onClick={() => setStartIndex((s) => s + 25)}>→</button>
          </div>
        }
      >
        {txs.isLoading ? <Loading /> : txs.error ? <ErrorState error={txs.error} onRetry={() => txs.refetch()} /> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Txid</th>
                  <th className="num">Entradas</th>
                  <th className="num">Salidas</th>
                  <th className="num">Importe de salida</th>
                  <th className="num hide-sm">Tasa</th>
                </tr>
              </thead>
              <tbody>{txs.data?.data.map((tx) => <TxRow key={tx.txid} tx={tx} />)}</tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

function AddressCell({ address }: { address: string | null }) {
  if (!address) return <span className="muted">sin dirección</span>;
  return (
    <Link to={`/address/${address}`} className="link mono" title={address}>
      {shortHash(address, 10)}
    </Link>
  );
}

export function TxPage() {
  const { txid = "" } = useParams();
  const { data, isLoading, error, refetch } = useTransaction(txid);
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorState error={error} onRetry={() => refetch()} />;
  const tx = data.data;
  const coinbase = tx.inputs.some((i) => i.is_coinbase);

  return (
    <>
      <PageHeader title="Transacción">
        <span className="mono break">{tx.txid}</span>
      </PageHeader>
      <div className="grid grid-4">
        <Panel title="Estado">
          <Stat
            label={tx.status.confirmed ? "Confirmada" : "En mempool"}
            value={tx.status.block_height !== null ? <Link className="link" to={`/block/${tx.status.block_hash}`}>#{formatInt(tx.status.block_height)}</Link> : "Pendiente"}
            hint={tx.status.block_time ? formatDateTime(tx.status.block_time) : "Se actualiza automáticamente"}
          />
        </Panel>
        <Panel title="Importe total de salidas"><Stat label="Suma de outputs" value={formatBTC(tx.total_output_sat)} /></Panel>
        <Panel title="Comisión">
          <Stat label={coinbase ? "Coinbase (sin comisión)" : formatFeeRate(tx.fee_rate)} value={coinbase ? "—" : formatBTC(tx.fee_sat)} />
        </Panel>
        <Panel title="Tamaño"><Stat label="Tamaño virtual" value={formatVBytes(tx.vsize)} hint={`${formatBytes(tx.size)} · ${formatInt(tx.weight)} WU`} /></Panel>
      </div>
      <div className="grid grid-2">
        <Panel title={`Entradas (${tx.inputs.length})`} subtitle="Hecho observable: salidas previas gastadas por esta transacción">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Dirección</th><th>Origen</th><th className="num">Importe</th></tr></thead>
              <tbody>
                {tx.inputs.map((i, idx) => (
                  <tr key={idx}>
                    <td>{i.is_coinbase ? <span className="tag">coinbase (nueva emisión)</span> : <AddressCell address={i.address} />}</td>
                    <td>{i.prev_txid ? <Link className="link mono" to={`/tx/${i.prev_txid}`}>{shortHash(i.prev_txid, 6)}:{i.prev_vout}</Link> : "—"}</td>
                    <td className="num">{formatBTC(i.value_sat)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel title={`Salidas (${tx.outputs.length})`} subtitle="Hecho observable: nuevas salidas creadas">
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Dirección</th><th>Tipo</th><th className="num">Importe</th></tr></thead>
              <tbody>
                {tx.outputs.map((o) => (
                  <tr key={o.index}>
                    <td className="muted">{o.index}</td>
                    <td><AddressCell address={o.address} /></td>
                    <td className="muted small">{o.script_type ?? "—"}</td>
                    <td className="num">{formatBTC(o.value_sat)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
      <p className="muted small">
        Las direcciones son identificadores públicos. Bitcoin Intelligence no atribuye identidades a direcciones sin pruebas verificables.
      </p>
      <Panel title="Metadatos" meta={<Freshness meta={data.meta} />}>
        <KeyValue rows={[["Versión", tx.version], ["Locktime", tx.locktime], ["Suma de entradas", formatBTC(tx.total_input_sat)]]} />
      </Panel>
    </>
  );
}

export function AddressPage() {
  const { address = "" } = useParams();
  const info = useAddress(address);
  const [cursor, setCursor] = useState<string[]>([]);
  const after = cursor[cursor.length - 1];
  const txs = useAddressTxs(address, after);

  if (info.isLoading) return <Loading />;
  if (info.error || !info.data) return <ErrorState error={info.error} onRetry={() => info.refetch()} />;
  const a = info.data.data;
  const list = txs.data?.data ?? [];
  const lastConfirmed = [...list].reverse().find((t) => t.status.confirmed);

  return (
    <>
      <PageHeader title="Dirección">
        <span className="mono break">{a.address}</span>
      </PageHeader>
      <div className="grid grid-4">
        <Panel title="Saldo confirmado"><Stat label="Recibido − gastado" value={formatBTC(a.confirmed_balance_sat)} /></Panel>
        <Panel title="Total recibido"><Stat label={`${formatInt(a.chain.funded_txo_count)} salidas`} value={formatBTC(a.chain.funded_sum_sat)} /></Panel>
        <Panel title="Total gastado"><Stat label={`${formatInt(a.chain.spent_txo_count)} salidas`} value={formatBTC(a.chain.spent_sum_sat)} /></Panel>
        <Panel title="Transacciones">
          <Stat
            label="Confirmadas"
            value={formatInt(a.chain.tx_count)}
            hint={a.mempool.tx_count ? `${a.mempool.tx_count} pendientes (${formatBTC(a.unconfirmed_delta_sat)})` : "Sin pendientes"}
          />
        </Panel>
      </div>
      <Panel
        title="Historial de transacciones"
        subtitle="Efecto neto sobre esta dirección"
        meta={<Freshness meta={txs.data?.meta ?? info.data.meta} />}
        actions={
          <div className="pager">
            <button className="btn btn-ghost" disabled={cursor.length === 0} onClick={() => setCursor((c) => c.slice(0, -1))}>← Más recientes</button>
            <button
              className="btn btn-ghost"
              disabled={!lastConfirmed || list.length < 25 || txs.isFetching}
              onClick={() => lastConfirmed && setCursor((c) => [...c, lastConfirmed.txid])}
            >
              Anteriores →
            </button>
          </div>
        }
      >
        {txs.isLoading ? <Loading /> : txs.error ? <ErrorState error={txs.error} onRetry={() => txs.refetch()} /> : list.length === 0 ? (
          <Empty>Esta dirección no tiene transacciones.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Txid</th><th>Bloque</th><th className="num">Recibido</th><th className="num">Enviado</th><th className="num">Neto</th></tr>
              </thead>
              <tbody>
                {list.map((t) => (
                  <tr key={t.txid}>
                    <td><HashLink to={`/tx/${t.txid}`} hash={t.txid} /></td>
                    <td>{t.status.block_height !== null ? formatInt(t.status.block_height) : <span className="tag">mempool</span>}</td>
                    <td className="num">{formatBTC(t.received_sat)}</td>
                    <td className="num">{formatBTC(t.sent_sat)}</td>
                    <td className={`num ${t.net_sat >= 0 ? "pos" : "neg"}`}>{t.net_sat >= 0 ? "+" : ""}{formatBTC(t.net_sat)}</td>
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
