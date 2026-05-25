export interface Dataset {
  dataset_id: string;
  original_filename: string;
  status: "pending" | "processing" | "ready" | "failed";
  row_count: number | null;
  column_count: number | null;
  created_at: string;
  schema_info?: Record<string, ColumnInfo>;
  column_tags?: Record<string, string>;
}

export interface ColumnInfo {
  dtype: string;
  null_count: number;
  null_pct: number;
  unique_count: number;
  stats?: {
    mean: number | null;
    std: number | null;
    min: number | null;
    max: number | null;
    p25: number | null;
    p50: number | null;
    p75: number | null;
  };
  outlier_count?: number;
  sample_values?: string[];
}

export interface Document {
  document_id: string;
  original_filename: string;
  status: "pending" | "processing" | "ready" | "failed";
  chunk_count: number | null;
  page_count: number | null;
  created_at: string;
}

export interface RetrievedChunk {
  text: string;
  metadata: {
    document_id: string;
    tenant_id: string;
    page: number;
    type: "text" | "table";
    chunk_index: number;
    embedding_model: string;
  };
  similarity_score: number;
  rerank_score?: number;
}

export interface SqlQueryResult {
  sql: string;
  rows: Record<string, unknown>[];
  row_count: number;
  error: string | null;
}

export interface Recommendation {
  action: string;
  confidence: "high" | "medium" | "low";
  confidence_rationale: string;
  document_evidence: Array<{
    text: string;
    source: string;
    page: number;
    relevance: string;
  }>;
  sql_evidence: Array<{
    sql: string;
    key_finding: string;
    row_summary: string;
  }>;
  conflicts: string[];
  reasoning_steps: string[];
  uncertainty_sources: string[];
}

export interface QueryResponse {
  session_id: string;
  recommendation_id: string;
  audit_record_id: string;
  recommendation: Recommendation;
  reasoning_trace: {
    sql_queries: SqlQueryResult[];
    retrieved_chunks: RetrievedChunk[];
  };
}

export interface AuditRecord {
  id: string;
  tenant_id: string;
  session_id: string | null;
  recommendation_id: string | null;
  query_text: string;
  active_dataset_ids: string[];
  active_document_ids: string[];
  llm_model: string;
  embed_model: string;
  prompt_version: string;
  sql_queries: SqlQueryResult[];
  retrieved_chunks: RetrievedChunk[];
  raw_model_output: string | null;
  recommendation: Recommendation | null;
  user_action: "accept" | "reject" | "review" | null;
  user_comment: string | null;
  action_at: string | null;
  scenario_label: string | null;
  scenario_assumptions: Record<string, unknown> | null;
  created_at: string;
}

export interface ChatSession {
  session_id: string;
  title: string | null;
  turn_count: number;
  active_dataset_ids: string[];
  active_document_ids: string[];
  last_active_at: string;
  created_at: string;
  context_summary?: string;
  messages?: Array<{ role: string; content: string; turn: number }>;
}
