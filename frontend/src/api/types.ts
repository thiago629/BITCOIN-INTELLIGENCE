// Mirrors backend/app/domain/models.py and the API envelopes.
// Amounts are integers in satoshis; dates are ISO-8601 UTC strings.

export interface DataMeta {
  source: string;
  fetched_at: string;
  cached: boolean;
  age_seconds: number;
  fallback_used: boolean;
}

export interface ApiResponse<T> {
  data: T;
  meta: DataMeta;
}

export interface Section<T> {
  data: T | null;
  meta: DataMeta | null;
  error: string | null;
}

export interface Block {
  hash: string;
  height: number;
  timestamp: string;
  median_time: string | null;
  tx_count: number;
  size: number;
  weight: number;
  version: number | null;
  merkle_root: string | null;
  previous_block_hash: string | null;
  nonce: number | null;
  bits: number | null;
  difficulty: number | null;
  total_fees_sat: number | null;
  reward_sat: number | null;
  median_fee_rate: number | null;
  avg_fee_rate: number | null;
}

export interface TxStatus {
  confirmed: boolean;
  block_height: number | null;
  block_hash: string | null;
  block_time: string | null;
}

export interface TxInput {
  prev_txid: string | null;
  prev_vout: number | null;
  is_coinbase: boolean;
  address: string | null;
  value_sat: number | null;
  script_type: string | null;
}

export interface TxOutput {
  index: number;
  address: string | null;
  value_sat: number;
  script_type: string | null;
}

export interface Transaction {
  txid: string;
  version: number;
  locktime: number;
  size: number;
  weight: number;
  vsize: number;
  fee_sat: number | null;
  fee_rate: number | null;
  status: TxStatus;
  inputs: TxInput[];
  outputs: TxOutput[];
  total_input_sat: number | null;
  total_output_sat: number;
}

export interface AddressStats {
  funded_txo_count: number;
  funded_sum_sat: number;
  spent_txo_count: number;
  spent_sum_sat: number;
  tx_count: number;
}

export interface AddressInfo {
  address: string;
  chain: AddressStats;
  mempool: AddressStats;
  confirmed_balance_sat: number;
  unconfirmed_delta_sat: number;
}

export interface AddressTx {
  txid: string;
  status: TxStatus;
  fee_sat: number | null;
  received_sat: number;
  sent_sat: number;
  net_sat: number;
}

export interface MempoolStats {
  count: number;
  vsize: number;
  total_fee_sat: number;
  fee_histogram: [number, number][];
}

export interface FeeEstimates {
  fastest: number;
  half_hour: number;
  hour: number;
  economy: number;
  minimum: number;
  method: "recommended" | "target_estimates";
}

export interface DifficultyAdjustment {
  progress_percent: number;
  difficulty_change_percent: number;
  estimated_retarget_date: string;
  remaining_blocks: number;
  next_retarget_height: number;
  previous_retarget_percent: number | null;
}

export interface NetworkSummary {
  tip_height: Section<number>;
  mempool: Section<MempoolStats>;
  fees: Section<FeeEstimates>;
  difficulty: Section<DifficultyAdjustment>;
}

export interface StoredMeta {
  source: string;
  generated_at: string;
  records: number;
}

export interface StoredBlock {
  height: number;
  hash: string;
  timestamp: string;
  tx_count: number;
  size: number;
  weight: number;
  total_fees_sat: number | null;
  reward_sat: number | null;
  median_fee_rate: number | null;
  avg_fee_rate: number | null;
  source: string;
  ingested_at: string;
}

export interface StoredSnapshot {
  captured_at: string;
  tip_height: number | null;
  mempool_count: number | null;
  mempool_vsize: number | null;
  mempool_total_fee_sat: number | null;
  fee_fastest: number | null;
  fee_half_hour: number | null;
  fee_hour: number | null;
  fee_economy: number | null;
  source: string;
}

export interface ProviderStatus {
  key: string;
  name: string;
  capabilities: string[];
  healthy: boolean;
  in_cooldown: boolean;
  cooldown_remaining_s: number;
  consecutive_failures: number;
  total_requests: number;
  total_failures: number;
  last_error: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  time: string;
  database: { ok: boolean; backend: string };
  cache: { entries: number; hits: number; misses: number };
  providers: ProviderStatus[];
  ingestion: {
    enabled: boolean;
    running: boolean;
    interval_s: number | null;
    last_run_at: string | null;
    last_status: string | null;
    stored_blocks: number;
  };
}

export interface IngestionRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "success" | "partial" | "failed";
  blocks_stored: number;
  snapshot_stored: boolean;
  sources: string | null;
  error: string | null;
}

export interface SearchResult {
  type: "block" | "transaction" | "address";
  id: string;
}
