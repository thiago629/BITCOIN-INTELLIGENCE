import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiSend } from "./client";
import type {
  AddressInfo,
  AlertEventList,
  AlertRule,
  AlertRuleInput,
  WhaleDetail,
  WhaleList,
  WhaleStats,
  AddressTx,
  ApiResponse,
  Block,
  Health,
  IngestionRun,
  NetworkSummary,
  StoredBlock,
  StoredMeta,
  StoredSnapshot,
  Transaction,
} from "./types";

const enc = encodeURIComponent;

export const useNetworkSummary = () =>
  useQuery({
    queryKey: ["network-summary"],
    queryFn: ({ signal }) => apiGet<NetworkSummary>("/network/summary", signal),
    refetchInterval: 20_000,
  });

export const useRecentBlocks = (startHeight?: number) =>
  useQuery({
    queryKey: ["blocks", startHeight ?? "tip"],
    queryFn: ({ signal }) =>
      apiGet<ApiResponse<Block[]>>(
        startHeight === undefined ? "/blocks/recent" : `/blocks/recent?start_height=${startHeight}`,
        signal,
      ),
    refetchInterval: startHeight === undefined ? 30_000 : false,
    placeholderData: keepPreviousData,
  });

export const useBlock = (hash: string) =>
  useQuery({
    queryKey: ["block", hash],
    queryFn: ({ signal }) => apiGet<ApiResponse<Block>>(`/blocks/${enc(hash)}`, signal),
  });

export const useBlockTxs = (hash: string, startIndex: number) =>
  useQuery({
    queryKey: ["block-txs", hash, startIndex],
    queryFn: ({ signal }) =>
      apiGet<ApiResponse<Transaction[]>>(`/blocks/${enc(hash)}/txs?start_index=${startIndex}`, signal),
    placeholderData: keepPreviousData,
  });

export const useTransaction = (txid: string) =>
  useQuery({
    queryKey: ["tx", txid],
    queryFn: ({ signal }) => apiGet<ApiResponse<Transaction>>(`/tx/${enc(txid)}`, signal),
    refetchInterval: (q) => (q.state.data && !q.state.data.data.status.confirmed ? 20_000 : false),
  });

export const useAddress = (address: string) =>
  useQuery({
    queryKey: ["address", address],
    queryFn: ({ signal }) => apiGet<ApiResponse<AddressInfo>>(`/address/${enc(address)}`, signal),
  });

export const useAddressTxs = (address: string, afterTxid?: string) =>
  useQuery({
    queryKey: ["address-txs", address, afterTxid ?? "first"],
    queryFn: ({ signal }) =>
      apiGet<ApiResponse<AddressTx[]>>(
        `/address/${enc(address)}/txs${afterTxid ? `?after_txid=${afterTxid}` : ""}`,
        signal,
      ),
    placeholderData: keepPreviousData,
  });

export const useBlockHistory = (limit = 144) =>
  useQuery({
    queryKey: ["history-blocks", limit],
    queryFn: ({ signal }) =>
      apiGet<{ data: StoredBlock[]; meta: StoredMeta }>(`/history/blocks?limit=${limit}`, signal),
    refetchInterval: 60_000,
  });

export const useNetworkHistory = (hours = 24) =>
  useQuery({
    queryKey: ["history-network", hours],
    queryFn: ({ signal }) =>
      apiGet<{ data: StoredSnapshot[]; meta: StoredMeta }>(`/history/network?hours=${hours}`, signal),
    refetchInterval: 60_000,
  });

export const useHealth = () =>
  useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => apiGet<Health>("/health", signal),
    refetchInterval: 15_000,
  });

export const useIngestionRuns = () =>
  useQuery({
    queryKey: ["ingestion-runs"],
    queryFn: ({ signal }) => apiGet<IngestionRun[]>("/system/ingestion-runs?limit=20", signal),
    refetchInterval: 30_000,
  });

// ---- Whale Tracker ---------------------------------------------------------

export interface WhaleFilters {
  min_btc?: string;
  max_btc?: string;
  since?: string;
  until?: string;
  status?: "all" | "confirmed" | "unconfirmed";
  sort?: "time" | "value";
  offset?: number;
  limit?: number;
}

export function whaleQuery(f: WhaleFilters): string {
  const p = new URLSearchParams();
  if (f.min_btc) p.set("min_btc", f.min_btc);
  if (f.max_btc) p.set("max_btc", f.max_btc);
  // <input type="date"> gives YYYY-MM-DD; interpret as UTC day boundaries.
  if (f.since) p.set("since", `${f.since}T00:00:00Z`);
  if (f.until) p.set("until", `${f.until}T23:59:59Z`);
  if (f.status && f.status !== "all") p.set("status", f.status);
  if (f.sort && f.sort !== "time") p.set("sort", f.sort);
  p.set("limit", String(f.limit ?? 25));
  if (f.offset) p.set("offset", String(f.offset));
  return p.toString();
}

export const useWhales = (f: WhaleFilters) =>
  useQuery({
    queryKey: ["whales", f],
    queryFn: ({ signal }) => apiGet<WhaleList>(`/whales?${whaleQuery(f)}`, signal),
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  });

export const useWhaleStats = (hours = 24) =>
  useQuery({
    queryKey: ["whale-stats", hours],
    queryFn: ({ signal }) => apiGet<WhaleStats>(`/whales/stats?hours=${hours}`, signal),
    refetchInterval: 30_000,
  });

export const useWhaleDetail = (txid: string) =>
  useQuery({
    queryKey: ["whale", txid],
    queryFn: ({ signal }) => apiGet<WhaleDetail>(`/whales/${enc(txid)}`, signal),
    refetchInterval: (q) => (q.state.data && !q.state.data.whale.confirmed ? 30_000 : false),
  });

// ---- Alerts --------------------------------------------------------------------

export const useAlertRules = () =>
  useQuery({
    queryKey: ["alert-rules"],
    queryFn: ({ signal }) => apiGet<AlertRule[]>("/alerts/rules", signal),
    refetchInterval: 30_000,
  });

export const useAlertEvents = (offset = 0) =>
  useQuery({
    queryKey: ["alert-events", offset],
    queryFn: ({ signal }) => apiGet<AlertEventList>(`/alerts/events?limit=25&offset=${offset}`, signal),
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  });

function useInvalidateAlerts() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["alert-rules"] });
    void qc.invalidateQueries({ queryKey: ["alert-events"] });
  };
}

export function useCreateRule() {
  const invalidate = useInvalidateAlerts();
  return useMutation({
    mutationFn: (body: AlertRuleInput) => apiSend<AlertRule>("POST", "/alerts/rules", body),
    onSuccess: invalidate,
  });
}

export function useUpdateRule() {
  const invalidate = useInvalidateAlerts();
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: number } & Partial<AlertRuleInput>) =>
      apiSend<AlertRule>("PATCH", `/alerts/rules/${id}`, patch),
    onSuccess: invalidate,
  });
}

export function useDeleteRule() {
  const invalidate = useInvalidateAlerts();
  return useMutation({
    mutationFn: (id: number) => apiSend<void>("DELETE", `/alerts/rules/${id}`),
    onSuccess: invalidate,
  });
}
