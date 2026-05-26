import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Database, FileText, Layers3, Loader2, Shield, Table2 } from "lucide-react";
import { Link } from "react-router-dom";
import { listDatasets, listDocuments } from "../api/client";
import UploadZone from "../components/UploadZone";
import type { Dataset, Document } from "../types";

const statusTone: Record<string, string> = {
  ready: "badge-green",
  pending: "badge-gray",
  processing: "badge-blue",
  failed: "badge-red",
};

function StatusPill({ status }: { status: string }) {
  return <span className={statusTone[status] || "badge-gray"}>{status}</span>;
}

export default function Dashboard() {
  const { data: datasets, refetch: refetchDatasets, isLoading: loadingDatasets } = useQuery<Dataset[]>({
    queryKey: ["datasets"],
    queryFn: () => listDatasets().then((r) => r.data),
    refetchInterval: 5000,
  });

  const { data: documents, refetch: refetchDocuments, isLoading: loadingDocuments } = useQuery<Document[]>({
    queryKey: ["documents"],
    queryFn: () => listDocuments().then((r) => r.data),
    refetchInterval: 5000,
  });

  const readyDatasets = datasets?.filter((dataset) => dataset.status === "ready") || [];
  const readyDocuments = documents?.filter((document) => document.status === "ready") || [];

  const handleUploaded = () => {
    refetchDatasets();
    refetchDocuments();
  };

  return (
    <div className="space-y-8">
      <section className="grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
        <div className="panel overflow-hidden p-8 md:p-10">
          <div className="eyebrow">Data Workspace</div>
          <h1 className="mt-4 text-4xl font-bold tracking-tight text-white md:text-5xl">
            Prepare the governed working set before you ask the model to recommend anything.
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-7 body-muted">
            LenAI treats source preparation as a first-class operation. Datasets become SQL-queryable tables, PDFs
            become indexed retrieval context, and both are tracked as active assets for downstream decisions and audit.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/query" className="btn-primary">
              Open decision studio
              <ArrowRight size={16} />
            </Link>
            <Link to="/audit" className="btn-secondary">
              Inspect audit ledger
            </Link>
          </div>
        </div>

        <div className="panel p-7">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-400/10 text-emerald-200">
              <Shield size={20} />
            </div>
            <div>
              <div className="text-base font-semibold text-white">Operational posture</div>
              <div className="text-sm body-muted">Everything ready here becomes part of the analyst’s controlled context.</div>
            </div>
          </div>

          <div className="space-y-4 text-sm leading-6 body-muted">
            <p>Use this page to load the exact dataset and document set that should participate in reasoning.</p>
            <p>Status polling reflects backend ingestion state, so analysts can see whether an asset is still extracting, embedding, or ready.</p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {[
          {
            title: "Ready datasets",
            value: readyDatasets.length,
            body: "Structured sources available for SQL analysis",
            icon: Database,
            accent: "text-emerald-200",
          },
          {
            title: "Indexed documents",
            value: readyDocuments.length,
            body: "Narrative sources retrievable for evidence",
            icon: FileText,
            accent: "text-sky-200",
          },
          {
            title: "Total chunks",
            value: readyDocuments.reduce((sum, document) => sum + (document.chunk_count || 0), 0),
            body: "Retrieval units active in vector search",
            icon: Layers3,
            accent: "text-amber-200",
          },
        ].map(({ title, value, body, icon: Icon, accent }) => (
          <div key={title} className="panel p-6">
            <div className="mb-5 flex items-center justify-between">
              <div className="text-sm font-medium text-slate-200">{title}</div>
              <div className={`flex h-11 w-11 items-center justify-center rounded-2xl bg-white/[0.04] ${accent}`}>
                <Icon size={18} />
              </div>
            </div>
            <div className="metric-value">{value}</div>
            <div className="mt-2 text-sm body-muted">{body}</div>
          </div>
        ))}
      </section>

      <section className="panel p-7 md:p-8">
        <div className="mb-5">
          <div className="section-title">Ingestion queue</div>
          <p className="mt-2 text-sm leading-6 body-muted">
            Upload the files you want in the active working set. CSV and Excel files feed the SQL path. PDFs feed the
            retrieval path.
          </p>
        </div>
        <UploadZone onUploaded={handleUploaded} />
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <div className="panel p-7">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-400/10 text-emerald-200">
              <Table2 size={18} />
            </div>
            <div>
              <div className="section-title">Dataset inventory</div>
              <div className="text-sm body-muted">SQL-queryable sources with inferred shape and readiness.</div>
            </div>
          </div>

          {loadingDatasets ? (
            <div className="flex items-center justify-center py-12 text-slate-400">
              <Loader2 size={20} className="animate-spin" />
            </div>
          ) : datasets?.length ? (
            <div className="space-y-3">
              {datasets.map((dataset) => (
                <div key={dataset.dataset_id} className="data-table-row">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-white">{dataset.original_filename}</div>
                    <div className="mt-1 text-xs body-muted">
                      {(dataset.row_count || 0).toLocaleString()} rows · {dataset.column_count || 0} columns
                    </div>
                  </div>
                  <StatusPill status={dataset.status} />
                </div>
              ))}
            </div>
          ) : (
            <div className="panel-subtle p-6 text-sm body-muted">No datasets uploaded yet.</div>
          )}
        </div>

        <div className="panel p-7">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-sky-400/10 text-sky-200">
              <FileText size={18} />
            </div>
            <div>
              <div className="section-title">Document inventory</div>
              <div className="text-sm body-muted">Indexed knowledge sources available for retrieval evidence.</div>
            </div>
          </div>

          {loadingDocuments ? (
            <div className="flex items-center justify-center py-12 text-slate-400">
              <Loader2 size={20} className="animate-spin" />
            </div>
          ) : documents?.length ? (
            <div className="space-y-3">
              {documents.map((document) => (
                <div key={document.document_id} className="data-table-row">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-white">{document.original_filename}</div>
                    <div className="mt-1 text-xs body-muted">
                      {document.chunk_count || 0} chunks · {document.page_count || 0} pages
                    </div>
                  </div>
                  <StatusPill status={document.status} />
                </div>
              ))}
            </div>
          ) : (
            <div className="panel-subtle p-6 text-sm body-muted">No documents uploaded yet.</div>
          )}
        </div>
      </section>
    </div>
  );
}
