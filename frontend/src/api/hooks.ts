import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";
import type {
  AddressInfo,
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
