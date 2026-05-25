import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, FileJson, FileText, Loader2 } from "lucide-react";
import toast from "react-hot-toast";
import { listAuditRecords, downloadAuditExport } from "../api/client";
import type { AuditRecord } from "../types";

const actionBadge = (action: string | null) => {
  if (!action) return <span className="badge-gray">Pending</span>;
  if (action === "accept") return <span className="badge-green">Accepted</span>;
  if (action === "reject") return <span className="badge-red">Rejected</span>;
  return <span className="badge-yellow">In Review</span>;
};

function ExportButton({ id, format }: { id: string; format: "json" | "pdf" }) {
  const [loading, setLoading] = useState(false);

  const handleDownload = async () => {
    setLoading(true);
    try {
      // Uses authenticated axios instance - Bearer token sent in request header.
      // Plain <a href> links cannot send custom headers, so downloads would fail.
      await downloadAuditExport(id, format);
    } catch {
      toast.error(`Export failed`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleDownload}
      disabled={loading}
      className="btn-secondary text-xs"
    >
      {loading ? (
        <Loader2 size={13} className="animate-spin" />
      ) : format === "json" ? (
        <FileJson size={13} />
      ) : (
        <FileText size={13} />
      )}
      Export {format.toUpperCase()}
    </button>
  );
}

function AuditRow({ record }: { record: AuditRecord }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-white hover:bg-gray-50 transition-colors text-left"
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">{record.query_text}</p>
          <p className="text-xs text-gray-400 mt-0.5">{new Date(record.created_at).toLocaleString()}</p>
        </div>
        <div className="flex items-center gap-3 ml-4 shrink-0">
          {actionBadge(record.user_action)}
          {open ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-gray-100 p-4 space-y-4 bg-gray-50">
          {record.recommendation && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Recommendation</p>
              <p className="text-sm font-medium text-gray-900">{record.recommendation.action}</p>
              <p className="text-xs text-gray-500 mt-0.5">Confidence: {record.recommendation.confidence}</p>
            </div>
          )}

          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Model Provenance</p>
            <div className="flex gap-4 text-xs text-gray-600">
              <span>LLM: <span className="font-mono">{record.llm_model}</span></span>
              <span>Embeddings: <span className="font-mono">{record.embed_model}</span></span>
              <span>Prompt: <span className="font-mono">{record.prompt_version}</span></span>
            </div>
          </div>

          {record.sql_queries?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">SQL Executed</p>
              {record.sql_queries.map((q, i) => (
                <pre key={i} className="text-xs font-mono bg-gray-900 text-green-400 rounded-lg px-3 py-2 mb-1 overflow-x-auto">
                  {q.sql}
                </pre>
              ))}
            </div>
          )}

          {record.retrieved_chunks?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Document Chunks Retrieved ({record.retrieved_chunks.length})
              </p>
              <div className="space-y-1">
                {record.retrieved_chunks.slice(0, 3).map((c, i) => (
                  <div key={i} className="text-xs bg-white border border-gray-100 rounded px-2 py-1">
                    <span className="text-gray-400 font-mono">p.{c.metadata.page}</span>{" "}
                    <span className="text-gray-400">score: {c.rerank_score?.toFixed(3)}</span>
                    <p className="text-gray-600 mt-0.5 line-clamp-2">{c.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {record.user_action && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Decision</p>
              <p className="text-sm">
                <span className="font-medium capitalize">{record.user_action}</span>
                {record.user_comment && <span className="text-gray-500"> - {record.user_comment}</span>}
              </p>
            </div>
          )}

          <div className="flex gap-2 pt-2 border-t border-gray-200">
            <ExportButton id={record.id} format="json" />
            <ExportButton id={record.id} format="pdf" />
          </div>
        </div>
      )}
    </div>
  );
}

export default function AuditPage() {
  const { data: records, isLoading } = useQuery<AuditRecord[]>({
    queryKey: ["audit"],
    queryFn: () => listAuditRecords().then((r) => r.data),
    refetchInterval: 10_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Audit Trail</h1>
        <p className="text-gray-500 text-sm mt-1">
          Immutable record of every query, SQL execution, retrieved evidence, and decision.
        </p>
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading...</p>}

      {records?.length === 0 && (
        <div className="card p-10 text-center">
          <p className="text-gray-400 text-sm">No audit records yet. Run a pricing query to get started.</p>
        </div>
      )}

      <div className="space-y-3">
        {records?.map((r) => <AuditRow key={r.id} record={r} />)}
      </div>
    </div>
  );
}
