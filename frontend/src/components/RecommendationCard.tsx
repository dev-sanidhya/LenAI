import { useState } from "react";
import {
  CheckCircle2, XCircle, AlertCircle, ChevronDown, ChevronUp,
  Database, FileText, TrendingUp, AlertTriangle, ClipboardCheck
} from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { submitAction } from "../api/client";
import type { QueryResponse } from "../types";

interface Props {
  response: QueryResponse;
  scenarioLabel?: string;
}

const confidenceBadge = (c: string) => {
  if (c === "high") return <span className="badge-green">High confidence</span>;
  if (c === "medium") return <span className="badge-yellow">Medium confidence</span>;
  return <span className="badge-red">Low confidence</span>;
};

export default function RecommendationCard({ response, scenarioLabel }: Props) {
  const [traceOpen, setTraceOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [actionDone, setActionDone] = useState<string | null>(null);
  const [rejectComment, setRejectComment] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [loading, setLoading] = useState(false);

  const rec = response.recommendation;
  const trace = response.reasoning_trace;

  const handleAction = async (action: "accept" | "review") => {
    setLoading(true);
    try {
      await submitAction(response.audit_record_id, action);
      setActionDone(action);
      toast.success(action === "accept" ? "Recommendation accepted" : "Flagged for human review");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Action failed");
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    if (!rejectComment.trim()) {
      toast.error("A comment is required when rejecting");
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
    <div className="card p-6 space-y-5">
      {scenarioLabel && (
        <div className="text-xs font-semibold text-brand-600 uppercase tracking-wide">{scenarioLabel}</div>
      )}

      {/* Main action */}
      <div>
        <div className="flex items-start gap-3">
          <TrendingUp size={20} className="text-brand-500 mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="font-semibold text-gray-900 text-lg leading-snug">{rec.action}</p>
            <div className="mt-2 flex items-center gap-2">
              {confidenceBadge(rec.confidence)}
              <span className="text-sm text-gray-500">{rec.confidence_rationale}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Conflicts */}
      {rec.conflicts && rec.conflicts.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <div className="flex items-center gap-2 text-amber-700 font-medium text-sm mb-1">
            <AlertTriangle size={15} />
            Conflicting Evidence Detected
          </div>
          <ul className="space-y-1">
            {rec.conflicts.map((c, i) => (
              <li key={i} className="text-sm text-amber-800">- {c}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Evidence panel */}
      <div>
        <button
          onClick={() => setEvidenceOpen((o) => !o)}
          className="flex items-center gap-2 text-sm font-medium text-gray-700 hover:text-gray-900"
        >
          {evidenceOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          Evidence Panel
          <span className="badge-blue ml-1">
            {(rec.document_evidence?.length || 0) + (rec.sql_evidence?.length || 0)} sources
          </span>
        </button>

        {evidenceOpen && (
          <div className="mt-3 space-y-3">
            {rec.document_evidence?.map((e, i) => (
              <div key={i} className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                <div className="flex items-center gap-2 mb-1">
                  <FileText size={13} className="text-gray-400" />
                  <span className="text-xs text-gray-500 font-mono">{e.source} p.{e.page}</span>
                </div>
                <p className="text-sm text-gray-700">{e.text}</p>
                <p className="text-xs text-brand-600 mt-1 italic">{e.relevance}</p>
              </div>
            ))}
            {rec.sql_evidence?.map((e, i) => (
              <div key={i} className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                <div className="flex items-center gap-2 mb-1">
                  <Database size={13} className="text-gray-400" />
                  <span className="text-xs text-gray-500 font-mono">SQL query</span>
                </div>
                <pre className="text-xs font-mono text-gray-600 whitespace-pre-wrap">{e.sql}</pre>
                <p className="text-sm text-gray-700 mt-1">{e.key_finding}</p>
                <p className="text-xs text-gray-500 mt-0.5">{e.row_summary}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Reasoning trace */}
      <div>
        <button
          onClick={() => setTraceOpen((o) => !o)}
          className="flex items-center gap-2 text-sm font-medium text-gray-700 hover:text-gray-900"
        >
          {traceOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          Reasoning Trace
        </button>

        {traceOpen && (
          <div className="mt-3 space-y-3">
            {rec.reasoning_steps?.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-2">Reasoning steps</p>
                <ol className="space-y-1">
                  {rec.reasoning_steps.map((step, i) => (
                    <li key={i} className="text-sm text-gray-700 flex gap-2">
                      <span className="text-gray-400 shrink-0">{i + 1}.</span>
                      {step}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {trace.sql_queries?.filter((q) => !q.error).map((q, i) => (
              <div key={i} className="bg-gray-900 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">SQL executed</p>
                <pre className="text-xs text-green-400 font-mono whitespace-pre-wrap">{q.sql}</pre>
                <p className="text-xs text-gray-400 mt-1">{q.row_count} rows returned</p>
              </div>
            ))}

            {rec.uncertainty_sources?.length > 0 && (
              <div className="bg-blue-50 rounded-lg p-3">
                <p className="text-xs font-medium text-blue-700 mb-1">Uncertainty sources</p>
                <ul className="space-y-0.5">
                  {rec.uncertainty_sources.map((u, i) => (
                    <li key={i} className="text-xs text-blue-800">- {u}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Actions */}
      {!actionDone ? (
        <div className="border-t border-gray-100 pt-4">
          <p className="text-xs text-gray-500 mb-3">Decision</p>
          {!showRejectInput ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleAction("accept")}
                disabled={loading}
                className="btn-primary bg-green-600 hover:bg-green-700"
              >
                <CheckCircle2 size={15} /> Accept
              </button>
              <button
                onClick={() => setShowRejectInput(true)}
                disabled={loading}
                className="btn-secondary text-red-600 border-red-200 hover:bg-red-50"
              >
                <XCircle size={15} /> Reject
              </button>
              <button
                onClick={() => handleAction("review")}
                disabled={loading}
                className="btn-secondary"
              >
                <AlertCircle size={15} /> Request Review
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <textarea
                className="w-full border border-gray-300 rounded-lg p-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-500"
                rows={2}
                placeholder="Required: explain why you are rejecting this recommendation"
                value={rejectComment}
                onChange={(e) => setRejectComment(e.target.value)}
              />
              <div className="flex gap-2">
                <button onClick={handleReject} disabled={loading} className="btn-primary bg-red-600 hover:bg-red-700">
                  Confirm Reject
                </button>
                <button onClick={() => setShowRejectInput(false)} className="btn-secondary">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="border-t border-gray-100 pt-4 flex items-center gap-2">
          <ClipboardCheck size={16} className="text-gray-500" />
          <span className="text-sm text-gray-600">
            Decision recorded: <span className="font-medium capitalize">{actionDone}</span>
          </span>
        </div>
      )}
    </div>
  );
}
