import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, FileJson, FileText, Loader2, ShieldCheck, Waypoints } from "lucide-react";
import toast from "react-hot-toast";
import { downloadAuditExport, listAuditRecords } from "../api/client";
import type { AuditRecord } from "../types";

const actionBadge = (action: string | null) => {
  if (!action) return <span className="badge-gray">Pending</span>;
  if (action === "accept") return <span className="badge-green">Accepted</span>;
  if (action === "reject") return <span className="badge-red">Rejected</span>;
  return <span className="badge-yellow">Review</span>;
};

function ExportButton({ id, format }: { id: string; format: "json" | "pdf" }) {
  const [loading, setLoading] = useState(false);

  const handleDownload = async () => {
    setLoading(true);
    try {
      await downloadAuditExport(id, format);
    } catch {
      toast.error("Export failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <button onClick={handleDownload} disabled={loading} className="btn-secondary">
      {loading ? <Loader2 size={14} className="animate-spin" /> : format === "json" ? <FileJson size={14} /> : <FileText size={14} />}
      Export {format.toUpperCase()}
    </button>
  );
}

function AuditRow({ record }: { record: AuditRecord }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="panel-subtle overflow-hidden">
      <button
        onClick={() => setOpen((state) => !state)}
        className="flex w-full items-center justify-between gap-4 px-5 py-5 text-left transition-colors hover:bg-white/[0.02]"
      >
        <div className="min-w-0 flex-1">
          <div className="truncate text-base font-semibold text-white">{record.query_text}</div>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.18em] body-muted">
            <span>{new Date(record.created_at).toLocaleString()}</span>
            <span className="mono">{record.id.slice(0, 8)}</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {actionBadge(record.user_action)}
          {open ? <ChevronUp size={18} className="text-slate-400" /> : <ChevronDown size={18} className="text-slate-400" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-white/6 px-5 py-5">
          <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-4">
              {record.recommendation && (
                <div className="rounded-[22px] border border-white/6 bg-white/[0.02] p-4">
                  <div className="mb-3 text-xs uppercase tracking-[0.18em] text-sky-200">Recommendation</div>
                  <div className="text-base font-semibold text-white">{record.recommendation.action}</div>
                  <div className="mt-2 text-sm body-muted">
                    Confidence: <span className="capitalize text-slate-100">{record.recommendation.confidence}</span>
                  </div>
                </div>
              )}

              <div className="rounded-[22px] border border-white/6 bg-white/[0.02] p-4">
                <div className="mb-3 text-xs uppercase tracking-[0.18em] text-sky-200">Model provenance</div>
                <div className="grid gap-2 text-sm text-slate-200 md:grid-cols-3">
                  <div>
                    <div className="body-muted">LLM</div>
                    <div className="mono mt-1">{record.llm_model}</div>
                  </div>
                  <div>
                    <div className="body-muted">Embeddings</div>
                    <div className="mono mt-1">{record.embed_model}</div>
                  </div>
                  <div>
                    <div className="body-muted">Prompt version</div>
                    <div className="mono mt-1">{record.prompt_version}</div>
                  </div>
                </div>
              </div>

              {record.sql_queries?.length > 0 && (
                <div className="rounded-[22px] border border-white/6 bg-white/[0.02] p-4">
                  <div className="mb-3 text-xs uppercase tracking-[0.18em] text-emerald-200">SQL trace</div>
                  <div className="space-y-3">
                    {record.sql_queries.map((query, index) => (
                      <pre key={index} className="mono overflow-x-auto rounded-2xl bg-slate-950/80 p-3 text-xs text-emerald-200">
                        {query.sql}
                      </pre>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-4">
              {record.retrieved_chunks?.length > 0 && (
                <div className="rounded-[22px] border border-white/6 bg-white/[0.02] p-4">
                  <div className="mb-3 text-xs uppercase tracking-[0.18em] text-sky-200">
                    Retrieved evidence ({record.retrieved_chunks.length})
                  </div>
                  <div className="space-y-3">
                    {record.retrieved_chunks.slice(0, 3).map((chunk, index) => (
                      <div key={index} className="rounded-2xl border border-white/6 bg-white/[0.02] p-3">
                        <div className="mb-2 text-xs body-muted">
                          page {chunk.metadata.page} · rerank {chunk.rerank_score?.toFixed(3) ?? "n/a"}
                        </div>
                        <p className="text-sm leading-6 text-slate-200">{chunk.text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="rounded-[22px] border border-white/6 bg-white/[0.02] p-4">
                <div className="mb-3 text-xs uppercase tracking-[0.18em] text-sky-200">Decision</div>
                <div className="text-sm text-slate-200">
                  {record.user_action ? (
                    <>
                      <span className="font-semibold capitalize">{record.user_action}</span>
                      {record.user_comment && <span className="body-muted"> · {record.user_comment}</span>}
                    </>
                  ) : (
                    <span className="body-muted">No analyst action recorded yet.</span>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                <ExportButton id={record.id} format="json" />
                <ExportButton id={record.id} format="pdf" />
              </div>
            </div>
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
    <div className="space-y-8">
      <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="panel p-8 md:p-10">
          <div className="eyebrow">Audit Ledger</div>
          <h1 className="mt-4 text-4xl font-bold tracking-tight text-white md:text-5xl">
            Review the immutable record behind every recommendation before it leaves the analyst workflow.
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-7 body-muted">
            This ledger is where recommendation provenance becomes operationally useful. It stores the prompt,
            retrieval evidence, SQL trace, model versions, and the analyst action that followed.
          </p>
        </div>

        <div className="panel p-7">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-400/10 text-sky-200">
              <ShieldCheck size={19} />
            </div>
            <div>
              <div className="text-base font-semibold text-white">Committee-ready output</div>
              <div className="text-sm body-muted">Export records as JSON for systems or PDF for human review.</div>
            </div>
          </div>

          <div className="space-y-3 text-sm leading-6 body-muted">
            <p>Audit is not an afterthought here. It is part of the product contract.</p>
            <p>Recommendations without provenance are suggestions. Recommendations with traceability can support real pricing review.</p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <div className="panel p-6">
          <div className="mb-3 text-sm font-medium text-slate-200">Audit records</div>
          <div className="metric-value">{records?.length || 0}</div>
        </div>
        <div className="panel p-6">
          <div className="mb-3 text-sm font-medium text-slate-200">Accepted actions</div>
          <div className="metric-value">{records?.filter((record) => record.user_action === "accept").length || 0}</div>
        </div>
        <div className="panel p-6">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-200">
            <Waypoints size={16} className="text-sky-200" />
            Pending review
          </div>
          <div className="metric-value">{records?.filter((record) => !record.user_action).length || 0}</div>
        </div>
      </section>

      {isLoading && (
        <div className="panel-subtle flex items-center justify-center py-12 text-slate-400">
          <Loader2 size={20} className="animate-spin" />
        </div>
      )}

      {!isLoading && records?.length === 0 && (
        <div className="panel-subtle p-6 text-sm body-muted">
          No audit records yet. Run a pricing query to create the first governed recommendation trail.
        </div>
      )}

      <div className="space-y-4">
        {records?.map((record) => (
          <AuditRow key={record.id} record={record} />
        ))}
      </div>
    </div>
  );
}
