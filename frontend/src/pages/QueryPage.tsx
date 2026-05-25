import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Send, Plus, Trash2, Loader2, History } from "lucide-react";
import toast from "react-hot-toast";
import { submitQuery, listDatasets, listDocuments, listSessions } from "../api/client";
import RecommendationCard from "../components/RecommendationCard";
import type { Dataset, Document, QueryResponse, ChatSession } from "../types";

interface ScenarioInput {
  label: string;
  assumptions: string;
}

export default function QueryPage() {
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selectedDatasets, setSelectedDatasets] = useState<string[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [responses, setResponses] = useState<QueryResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [scenarioMode, setScenarioMode] = useState(false);
  const [scenarios, setScenarios] = useState<ScenarioInput[]>([
    { label: "Base case", assumptions: "" },
    { label: "Scenario 2", assumptions: "" },
  ]);

  const { data: datasets } = useQuery<Dataset[]>({
    queryKey: ["datasets"],
    queryFn: () => listDatasets().then((r) => r.data),
  });

  const { data: documents } = useQuery<Document[]>({
    queryKey: ["documents"],
    queryFn: () => listDocuments().then((r) => r.data),
  });

  const { data: sessions } = useQuery<ChatSession[]>({
    queryKey: ["sessions"],
    queryFn: () => listSessions().then((r) => r.data),
  });

  const readyDatasets = datasets?.filter((d) => d.status === "ready") || [];
  const readyDocs = documents?.filter((d) => d.status === "ready") || [];

  const handleSubmit = async () => {
    if (!question.trim()) { toast.error("Enter a question"); return; }
    if (readyDatasets.length === 0 && readyDocs.length === 0) {
      toast.error("Upload at least one dataset or document first");
      return;
    }
    setLoading(true);
    try {
      if (scenarioMode) {
        const results: QueryResponse[] = [];
        for (const sc of scenarios) {
          let assumptions: Record<string, unknown> | undefined;
          try {
            assumptions = sc.assumptions ? JSON.parse(sc.assumptions) : undefined;
          } catch {
            toast.error(`Invalid JSON in "${sc.label}" assumptions`);
            setLoading(false);
            return;
          }
          const res = await submitQuery({
            question,
            session_id: sessionId || undefined,
            dataset_ids: selectedDatasets.length ? selectedDatasets : readyDatasets.map((d) => d.dataset_id),
            document_ids: selectedDocs.length ? selectedDocs : readyDocs.map((d) => d.document_id),
            scenario_assumptions: assumptions,
            scenario_label: sc.label,
            is_ephemeral: true, // Scenario runs are NOT written into conversational memory
          });
          if (!sessionId) setSessionId(res.data.session_id);
          results.push({ ...res.data, scenarioLabel: sc.label } as QueryResponse & { scenarioLabel: string });
        }
        setResponses((prev) => [...results, ...prev]);
      } else {
        const res = await submitQuery({
          question,
          session_id: sessionId || undefined,
          dataset_ids: selectedDatasets.length ? selectedDatasets : readyDatasets.map((d) => d.dataset_id),
          document_ids: selectedDocs.length ? selectedDocs : readyDocs.map((d) => d.document_id),
        });
        setSessionId(res.data.session_id);
        setResponses((prev) => [res.data, ...prev]);
      }
      setQuestion("");
      toast.success("Analysis complete");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Pricing Query</h1>
          <p className="text-gray-500 text-sm mt-1">Ask a pricing question in plain English</p>
        </div>
        {sessionId && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <History size={13} />
            Session active - context is remembered
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Left: context selectors */}
        <div className="space-y-4">
          <div className="card p-4">
            <p className="text-sm font-medium text-gray-700 mb-3">Active Datasets</p>
            {readyDatasets.length === 0 ? (
              <p className="text-xs text-gray-400">No ready datasets</p>
            ) : (
              <div className="space-y-2">
                {readyDatasets.map((d) => (
                  <label key={d.dataset_id} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedDatasets.includes(d.dataset_id)}
                      onChange={(e) =>
                        setSelectedDatasets((prev) =>
                          e.target.checked ? [...prev, d.dataset_id] : prev.filter((id) => id !== d.dataset_id)
                        )
                      }
                      className="accent-brand-500"
                    />
                    <span className="text-xs text-gray-700 truncate">{d.original_filename}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="card p-4">
            <p className="text-sm font-medium text-gray-700 mb-3">Active Documents</p>
            {readyDocs.length === 0 ? (
              <p className="text-xs text-gray-400">No indexed documents</p>
            ) : (
              <div className="space-y-2">
                {readyDocs.map((d) => (
                  <label key={d.document_id} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedDocs.includes(d.document_id)}
                      onChange={(e) =>
                        setSelectedDocs((prev) =>
                          e.target.checked ? [...prev, d.document_id] : prev.filter((id) => id !== d.document_id)
                        )
                      }
                      className="accent-brand-500"
                    />
                    <span className="text-xs text-gray-700 truncate">{d.original_filename}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {sessions && sessions.length > 0 && (
            <div className="card p-4">
              <p className="text-sm font-medium text-gray-700 mb-3">Resume Session</p>
              <div className="space-y-1">
                {sessions.slice(0, 5).map((s) => (
                  <button
                    key={s.session_id}
                    onClick={() => setSessionId(s.session_id)}
                    className={`w-full text-left text-xs px-2 py-1.5 rounded transition-colors ${
                      sessionId === s.session_id ? "bg-brand-50 text-brand-700" : "hover:bg-gray-50 text-gray-600"
                    }`}
                  >
                    {s.title || `Session (${s.turn_count} turns)`}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: query input + results */}
        <div className="col-span-2 space-y-4">
          {/* Scenario toggle */}
          <div className="card p-4">
            <div className="flex items-center justify-between mb-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={scenarioMode}
                  onChange={(e) => setScenarioMode(e.target.checked)}
                  className="accent-brand-500"
                />
                <span className="text-sm font-medium text-gray-700">Scenario comparison mode</span>
              </label>
            </div>

            {scenarioMode && (
              <div className="space-y-2 mb-4">
                {scenarios.map((sc, i) => (
                  <div key={i} className="flex gap-2">
                    <input
                      className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-32 focus:outline-none focus:ring-2 focus:ring-brand-500"
                      placeholder="Label"
                      value={sc.label}
                      onChange={(e) => setScenarios((prev) => prev.map((s, j) => j === i ? { ...s, label: e.target.value } : s))}
                    />
                    <input
                      className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-brand-500 font-mono"
                      placeholder='Assumptions JSON e.g. {"claims_increase": 0.15}'
                      value={sc.assumptions}
                      onChange={(e) => setScenarios((prev) => prev.map((s, j) => j === i ? { ...s, assumptions: e.target.value } : s))}
                    />
                    {i >= 2 && (
                      <button onClick={() => setScenarios((prev) => prev.filter((_, j) => j !== i))}>
                        <Trash2 size={15} className="text-red-400" />
                      </button>
                    )}
                  </div>
                ))}
                {scenarios.length < 3 && (
                  <button
                    onClick={() => setScenarios((prev) => [...prev, { label: `Scenario ${prev.length + 1}`, assumptions: "" }])}
                    className="text-xs text-brand-600 flex items-center gap-1 hover:underline"
                  >
                    <Plus size={12} /> Add scenario
                  </button>
                )}
              </div>
            )}

            <div className="flex gap-2">
              <textarea
                className="flex-1 border border-gray-300 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-500 min-h-[80px]"
                placeholder='Ask a pricing question... e.g. "Should we reprice motor insurance for under-25 drivers in the North?"'
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && e.metaKey) handleSubmit();
                }}
              />
              <button
                onClick={handleSubmit}
                disabled={loading || !question.trim()}
                className="btn-primary self-end"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                Analyse
              </button>
            </div>
          </div>

          {/* Results */}
          {scenarioMode && responses.length >= 2 && (
            <div className="grid grid-cols-2 gap-4">
              {responses.slice(0, scenarios.length).map((r, i) => (
                <RecommendationCard
                  key={r.audit_record_id}
                  response={r}
                  scenarioLabel={(r as QueryResponse & { scenarioLabel?: string }).scenarioLabel}
                />
              ))}
            </div>
          )}

          {!scenarioMode && responses.map((r) => (
            <RecommendationCard key={r.audit_record_id} response={r} />
          ))}
        </div>
      </div>
    </div>
  );
}
