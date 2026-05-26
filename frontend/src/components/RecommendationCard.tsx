import { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  Database,
  FileText,
  Loader2,
  SearchCheck,
  ShieldAlert,
  TrendingUp,
  XCircle,
} from "lucide-react";
import toast from "react-hot-toast";
import { submitAction } from "../api/client";
import type { QueryResponse } from "../types";

interface Props {
  response: QueryResponse;
  scenarioLabel?: string;
}

const confidenceBadge = (confidence: string) => {
  if (confidence === "high") return <span className="badge-green">High confidence</span>;
  if (confidence === "medium") return <span className="badge-yellow">Medium confidence</span>;
  return <span className="badge-red">Low confidence</span>;
};

export default function RecommendationCard({ response, scenarioLabel }: Props) {
  const [traceOpen, setTraceOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(true);
  const [actionDone, setActionDone] = useState<string | null>(null);
  const [rejectComment, setRejectComment] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [loading, setLoading] = useState(false);

  const recommendation = response.recommendation;
  const trace = response.reasoning_trace;

  const handleAction = async (action: "accept" | "review") => {
    setLoading(true);
    try {
      await submitAction(response.audit_record_id, action);
      setActionDone(action);
      toast.success(action === "accept" ? "Recommendation accepted" : "Flagged for review");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Action failed");
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    if (!rejectComment.trim()) {
      toast.error("A rejection comment is required");
      return;
    }
    setLoading(true);
    try {
      await submitAction(response.audit_record_id, "reject", rejectComment);
      setActionDone("reject");
      toast.success("Recommendation rejected");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Action failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <article className="panel overflow-hidden p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          {scenarioLabel && <div className="eyebrow mb-3">{scenarioLabel}</div>}
          <div className="flex items-start gap-4">
            <div className="mt-1 flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-400/10 text-sky-200">
              <TrendingUp size={20} />
            </div>
            <div>
              <h2 className="text-2xl font-semibold leading-9 text-white">{recommendation.action}</h2>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                {confidenceBadge(recommendation.confidence)}
                <span className="max-w-2xl text-sm leading-6 body-muted">{recommendation.confidence_rationale}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="panel-subtle px-4 py-3 text-right">
          <div className="text-xs uppercase tracking-[0.18em] body-muted">Audit record</div>
          <div className="mono mt-1 text-sm text-sky-100">{response.audit_record_id.slice(0, 8)}</div>
        </div>
      </div>

      {recommendation.conflicts?.length > 0 && (
        <div className="mt-6 rounded-[24px] border border-amber-300/16 bg-amber-300/8 p-5">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-amber-200">
            <ShieldAlert size={16} />
            Conflicting evidence surfaced
          </div>
          <ul className="space-y-2 text-sm leading-6 text-amber-100/90">
            {recommendation.conflicts.map((conflict, index) => (
              <li key={index}>- {conflict}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <section className="panel-subtle p-5">
          <button
            onClick={() => setEvidenceOpen((open) => !open)}
            className="flex w-full items-center justify-between gap-3 text-left"
          >
            <div>
              <div className="text-base font-semibold text-white">Evidence deck</div>
              <div className="mt-1 text-sm body-muted">
                Document passages and SQL-backed findings surfaced to support the recommendation.
              </div>
            </div>
            {evidenceOpen ? <ChevronUp size={18} className="text-slate-400" /> : <ChevronDown size={18} className="text-slate-400" />}
          </button>

          {evidenceOpen && (
            <div className="mt-5 space-y-4">
              {recommendation.document_evidence?.map((evidence, index) => (
                <div key={index} className="rounded-[22px] border border-white/6 bg-white/[0.02] p-4">
                  <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-sky-200">
                    <FileText size={14} />
                    {evidence.source} · page {evidence.page}
                  </div>
                  <p className="text-sm leading-6 text-slate-100">{evidence.text}</p>
                  <p className="mt-3 text-sm leading-6 text-sky-100/90">{evidence.relevance}</p>
                </div>
              ))}

              {recommendation.sql_evidence?.map((evidence, index) => (
                <div key={index} className="rounded-[22px] border border-white/6 bg-white/[0.02] p-4">
                  <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-emerald-200">
                    <Database size={14} />
                    SQL evidence
                  </div>
                  <pre className="mono overflow-x-auto whitespace-pre-wrap rounded-2xl bg-slate-950/80 p-3 text-xs text-emerald-200">
                    {evidence.sql}
                  </pre>
                  <p className="mt-3 text-sm text-slate-100">{evidence.key_finding}</p>
                  <p className="mt-1 text-sm body-muted">{evidence.row_summary}</p>
                </div>
              ))}

              {recommendation.document_evidence?.length === 0 && recommendation.sql_evidence?.length === 0 && (
                <div className="rounded-[22px] border border-dashed border-white/10 p-4 text-sm body-muted">
                  No explicit evidence blocks were returned in the structured recommendation.
                </div>
              )}
            </div>
          )}
        </section>

        <section className="space-y-4">
          <div className="panel-subtle p-5">
            <div className="mb-4 flex items-center gap-2 text-base font-semibold text-white">
              <SearchCheck size={16} className="text-sky-200" />
              Reasoning summary
            </div>
            <ol className="space-y-3">
              {recommendation.reasoning_steps?.map((step, index) => (
                <li key={index} className="flex gap-3 text-sm leading-6 text-slate-200">
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/[0.06] text-xs text-sky-200">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>

          {recommendation.uncertainty_sources?.length > 0 && (
            <div className="panel-subtle p-5">
              <div className="mb-3 flex items-center gap-2 text-base font-semibold text-white">
                <AlertTriangle size={16} className="text-amber-200" />
                Uncertainty sources
              </div>
              <ul className="space-y-2 text-sm leading-6 text-slate-200">
                {recommendation.uncertainty_sources.map((item, index) => (
                  <li key={index}>- {item}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="panel-subtle p-5">
            <button onClick={() => setTraceOpen((open) => !open)} className="flex w-full items-center justify-between gap-3 text-left">
              <div>
                <div className="text-base font-semibold text-white">Execution trace</div>
                <div className="mt-1 text-sm body-muted">Inspectable SQL path and retrieved document chunks.</div>
              </div>
              {traceOpen ? <ChevronUp size={18} className="text-slate-400" /> : <ChevronDown size={18} className="text-slate-400" />}
            </button>

            {traceOpen && (
              <div className="mt-5 space-y-4">
                {trace.sql_queries?.map((query, index) => (
                  <div key={index} className="rounded-[22px] bg-slate-950/75 p-4">
                    <div className="mb-2 text-xs uppercase tracking-[0.18em] text-slate-400">SQL execution</div>
                    <pre className="mono whitespace-pre-wrap text-xs text-emerald-200">{query.sql}</pre>
                    <div className="mt-2 text-xs text-slate-400">
                      {query.error ? `Error: ${query.error}` : `${query.row_count} rows returned`}
                    </div>
                  </div>
                ))}

                {trace.retrieved_chunks?.slice(0, 3).map((chunk, index) => (
                  <div key={index} className="rounded-[22px] border border-white/6 bg-white/[0.02] p-4">
                    <div className="mb-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                      Chunk p.{chunk.metadata.page} · rerank {chunk.rerank_score?.toFixed(3) ?? "n/a"}
                    </div>
                    <p className="text-sm leading-6 text-slate-200">{chunk.text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="mt-6 border-t border-white/6 pt-6">
        {!actionDone ? (
          <>
            <div className="mb-4 text-sm font-medium text-slate-200">Analyst decision</div>
            {!showRejectInput ? (
              <div className="flex flex-wrap gap-3">
                <button onClick={() => handleAction("accept")} disabled={loading} className="btn-primary bg-none">
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                  Accept
                </button>
                <button
                  onClick={() => setShowRejectInput(true)}
                  disabled={loading}
                  className="btn-secondary border-rose-300/20 text-rose-200 hover:bg-rose-300/10"
                >
                  <XCircle size={16} />
                  Reject
                </button>
                <button onClick={() => handleAction("review")} disabled={loading} className="btn-secondary">
                  <AlertCircle size={16} />
                  Request review
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <textarea
                  rows={3}
                  className="input resize-none"
                  placeholder="Required: explain why this recommendation should be rejected."
                  value={rejectComment}
                  onChange={(e) => setRejectComment(e.target.value)}
                />
                <div className="flex flex-wrap gap-3">
                  <button onClick={handleReject} disabled={loading} className="btn-primary">
                    Confirm rejection
                  </button>
                  <button onClick={() => setShowRejectInput(false)} className="btn-secondary">
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="flex items-center gap-3 rounded-[22px] border border-emerald-300/14 bg-emerald-300/8 px-4 py-4 text-sm text-emerald-100">
            <ClipboardCheck size={18} className="text-emerald-200" />
            Decision recorded: <span className="font-semibold capitalize">{actionDone}</span>
          </div>
        )}
      </div>
    </article>
  );
}
