import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, History, Loader2, Plus, Sparkles, Trash2 } from "lucide-react";
import toast from "react-hot-toast";
import { listDatasets, listDocuments, listSessions, submitQuery } from "../api/client";
import RecommendationCard from "../components/RecommendationCard";
import type { ChatSession, Dataset, Document, QueryResponse } from "../types";

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
    { label: "Stress case", assumptions: "" },
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

  const readyDatasets = datasets?.filter((dataset) => dataset.status === "ready") || [];
  const readyDocuments = documents?.filter((document) => document.status === "ready") || [];

  const effectiveDatasetIds = selectedDatasets.length ? selectedDatasets : readyDatasets.map((dataset) => dataset.dataset_id);
  const effectiveDocumentIds = selectedDocs.length ? selectedDocs : readyDocuments.map((document) => document.document_id);

  const handleSubmit = async () => {
    if (!question.trim()) {
      toast.error("Enter a pricing question");
      return;
    }
    if (readyDatasets.length === 0 && readyDocuments.length === 0) {
      toast.error("Upload at least one ready dataset or document first");
      return;
    }

    setLoading(true);
    try {
      if (scenarioMode) {
        const scenarioResponses: QueryResponse[] = [];
        for (const scenario of scenarios) {
          let assumptions: Record<string, unknown> | undefined;
          try {
            assumptions = scenario.assumptions ? JSON.parse(scenario.assumptions) : undefined;
          } catch {
            toast.error(`Invalid JSON in "${scenario.label}" assumptions`);
            setLoading(false);
            return;
          }

          const res = await submitQuery({
            question,
            session_id: sessionId || undefined,
            dataset_ids: effectiveDatasetIds,
            document_ids: effectiveDocumentIds,
            scenario_assumptions: assumptions,
            scenario_label: scenario.label,
            is_ephemeral: true,
          });
          if (!sessionId) setSessionId(res.data.session_id);
          scenarioResponses.push({ ...res.data, scenarioLabel: scenario.label } as QueryResponse & { scenarioLabel: string });
        }
        setResponses((prev) => [...scenarioResponses, ...prev]);
      } else {
        const res = await submitQuery({
          question,
          session_id: sessionId || undefined,
          dataset_ids: effectiveDatasetIds,
          document_ids: effectiveDocumentIds,
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
    <div className="space-y-8">
      <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="panel p-8 md:p-10">
          <div className="eyebrow">Decision Studio</div>
          <h1 className="mt-4 text-4xl font-bold tracking-tight text-white md:text-5xl">
            Ask pricing questions against the active working set and inspect exactly how the answer was formed.
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-7 body-muted">
            The model uses two evidence paths in parallel: validated SQL over uploaded datasets and retrieval over
            indexed documents. The goal is not chat fluency. The goal is traceable analyst support.
          </p>
        </div>

        <div className="panel p-7">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-400/10 text-sky-200">
              <History size={19} />
            </div>
            <div>
              <div className="text-base font-semibold text-white">Session continuity</div>
              <div className="text-sm body-muted">Active datasets, documents, and prior turns can persist across follow-up questions.</div>
            </div>
          </div>

          <div className="space-y-3 text-sm leading-6 body-muted">
            <p>For the cleanest live demo, start a fresh session and keep scenario mode off for the first question.</p>
            <p>Use scenario mode only when you want to compare the same prompt across multiple explicit assumptions.</p>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <aside className="space-y-6">
          <div className="panel p-6">
            <div className="mb-4 text-base font-semibold text-white">Active working set</div>

            <div className="space-y-5">
              <div>
                <div className="mb-3 text-sm font-medium text-slate-200">Datasets</div>
                <div className="space-y-2">
                  {readyDatasets.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-white/10 px-4 py-3 text-sm body-muted">
                      No ready datasets
                    </div>
                  ) : (
                    readyDatasets.map((dataset) => (
                      <label key={dataset.dataset_id} className="data-table-row cursor-pointer">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-white">{dataset.original_filename}</div>
                          <div className="mt-1 text-xs body-muted">
                            {(dataset.row_count || 0).toLocaleString()} rows · {dataset.column_count || 0} columns
                          </div>
                        </div>
                        <input
                          type="checkbox"
                          checked={selectedDatasets.includes(dataset.dataset_id)}
                          onChange={(e) =>
                            setSelectedDatasets((prev) =>
                              e.target.checked ? [...prev, dataset.dataset_id] : prev.filter((id) => id !== dataset.dataset_id)
                            )
                          }
                          className="h-4 w-4 accent-sky-400"
                        />
                      </label>
                    ))
                  )}
                </div>
              </div>

              <div>
                <div className="mb-3 text-sm font-medium text-slate-200">Documents</div>
                <div className="space-y-2">
                  {readyDocuments.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-white/10 px-4 py-3 text-sm body-muted">
                      No indexed documents
                    </div>
                  ) : (
                    readyDocuments.map((document) => (
                      <label key={document.document_id} className="data-table-row cursor-pointer">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-white">{document.original_filename}</div>
                          <div className="mt-1 text-xs body-muted">
                            {document.chunk_count || 0} chunks · {document.page_count || 0} pages
                          </div>
                        </div>
                        <input
                          type="checkbox"
                          checked={selectedDocs.includes(document.document_id)}
                          onChange={(e) =>
                            setSelectedDocs((prev) =>
                              e.target.checked ? [...prev, document.document_id] : prev.filter((id) => id !== document.document_id)
                            )
                          }
                          className="h-4 w-4 accent-sky-400"
                        />
                      </label>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>

          {sessions && sessions.length > 0 && (
            <div className="panel p-6">
              <div className="mb-4 text-base font-semibold text-white">Resume a prior session</div>
              <div className="space-y-2">
                {sessions.slice(0, 5).map((session) => (
                  <button
                    key={session.session_id}
                    onClick={() => setSessionId(session.session_id)}
                    className={`w-full rounded-2xl px-4 py-3 text-left transition-colors ${
                      sessionId === session.session_id
                        ? "bg-sky-400/10 text-sky-100 shadow-[inset_0_0_0_1px_rgba(91,181,255,0.24)]"
                        : "bg-white/[0.02] text-slate-300 hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="text-sm font-medium">{session.title || `Session (${session.turn_count} turns)`}</div>
                    <div className="mt-1 text-xs body-muted">
                      {session.active_dataset_ids.length} datasets · {session.active_document_ids.length} documents
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>

        <div className="space-y-6">
          <div className="panel p-6 md:p-7">
            <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-base font-semibold text-white">Compose analyst question</div>
                <div className="mt-1 text-sm body-muted">
                  Ask in plain English. The backend will decide across SQL evidence and document evidence.
                </div>
              </div>
              <label className="flex cursor-pointer items-center gap-3 rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={scenarioMode}
                  onChange={(e) => setScenarioMode(e.target.checked)}
                  className="h-4 w-4 accent-sky-400"
                />
                Scenario comparison mode
              </label>
            </div>

            {scenarioMode && (
              <div className="mb-5 rounded-[24px] border border-sky-400/10 bg-sky-400/6 p-4">
                <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-sky-100">
                  <Sparkles size={16} />
                  Compare the same question under multiple assumptions
                </div>
                <div className="space-y-3">
                  {scenarios.map((scenario, index) => (
                    <div key={index} className="grid gap-3 md:grid-cols-[180px_1fr_auto]">
                      <input
                        className="input"
                        placeholder="Scenario label"
                        value={scenario.label}
                        onChange={(e) =>
                          setScenarios((prev) => prev.map((item, i) => (i === index ? { ...item, label: e.target.value } : item)))
                        }
                      />
                      <input
                        className="input mono"
                        placeholder='Assumptions JSON e.g. {"claims_increase": 0.15}'
                        value={scenario.assumptions}
                        onChange={(e) =>
                          setScenarios((prev) =>
                            prev.map((item, i) => (i === index ? { ...item, assumptions: e.target.value } : item))
                          )
                        }
                      />
                      {index >= 2 && (
                        <button onClick={() => setScenarios((prev) => prev.filter((_, i) => i !== index))} className="btn-secondary">
                          <Trash2 size={15} />
                        </button>
                      )}
                    </div>
                  ))}
                  {scenarios.length < 3 && (
                    <button
                      onClick={() => setScenarios((prev) => [...prev, { label: `Scenario ${prev.length + 1}`, assumptions: "" }])}
                      className="btn-secondary"
                    >
                      <Plus size={15} />
                      Add scenario
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-[1fr_auto]">
              <textarea
                className="input min-h-[170px] resize-none"
                placeholder='Ask a pricing question... e.g. "Should we reprice motor insurance for under-25 drivers in the Northern region?"'
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <button onClick={handleSubmit} disabled={loading || !question.trim()} className="btn-primary h-fit md:min-w-[180px]">
                {loading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
                {loading ? "Analysing..." : "Run analysis"}
              </button>
            </div>
          </div>

          {responses.length === 0 && (
            <div className="panel-subtle p-6 text-sm body-muted">
              Your recommendations will appear here. Start with a single question, then use a follow-up query in the
              same session to demonstrate memory continuity.
            </div>
          )}

          {scenarioMode && responses.length >= 2 ? (
            <div className="grid gap-5 2xl:grid-cols-2">
              {responses.slice(0, scenarios.length).map((response) => (
                <RecommendationCard
                  key={response.audit_record_id}
                  response={response}
                  scenarioLabel={(response as QueryResponse & { scenarioLabel?: string }).scenarioLabel}
                />
              ))}
            </div>
          ) : (
            <div className="space-y-5">
              {responses.map((response) => (
                <RecommendationCard key={response.audit_record_id} response={response} />
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
