import { useQuery } from "@tanstack/react-query";
import { FileText, Table2, Loader2, AlertCircle, Database } from "lucide-react";
import { listDatasets, listDocuments } from "../api/client";
import UploadZone from "../components/UploadZone";
import type { Dataset, Document } from "../types";

const StatusPill = ({ status }: { status: string }) => {
  const map: Record<string, string> = {
    ready: "badge-green",
    pending: "badge-gray",
    processing: "badge-blue",
    failed: "badge-red",
  };
  return <span className={map[status] || "badge-gray"}>{status}</span>;
};

export default function Dashboard() {
  const { data: datasets, refetch: refetchDatasets, isLoading: loadingDs } = useQuery<Dataset[]>({
    queryKey: ["datasets"],
    queryFn: () => listDatasets().then((r) => r.data),
    refetchInterval: 5000,
  });

  const { data: documents, refetch: refetchDocs, isLoading: loadingDocs } = useQuery<Document[]>({
    queryKey: ["documents"],
    queryFn: () => listDocuments().then((r) => r.data),
    refetchInterval: 5000,
  });

  const handleUploaded = () => {
    refetchDatasets();
    refetchDocs();
  };

  const readyDatasets = datasets?.filter((d) => d.status === "ready") || [];
  const readyDocs = documents?.filter((d) => d.status === "ready") || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Data Sources</h1>
        <p className="text-gray-500 text-sm mt-1">
          Upload policy CSVs, actuarial PDFs, and regulatory documents. The system will process them automatically.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Datasets ready", value: readyDatasets.length, icon: Database, color: "text-green-600" },
          { label: "Documents indexed", value: readyDocs.length, icon: FileText, color: "text-blue-600" },
          {
            label: "Total chunks",
            value: readyDocs.reduce((sum, d) => sum + (d.chunk_count || 0), 0),
            icon: Table2,
            color: "text-purple-600",
          },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="card p-5">
            <div className="flex items-center gap-3">
              <Icon size={20} className={color} />
              <div>
                <p className="text-2xl font-bold text-gray-900">{value}</p>
                <p className="text-xs text-gray-500">{label}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Upload */}
      <div className="card p-6">
        <h2 className="font-semibold text-gray-900 mb-4">Upload Files</h2>
        <UploadZone onUploaded={handleUploaded} />
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Datasets */}
        <div className="card p-5">
          <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Table2 size={16} className="text-green-500" /> Datasets
          </h2>
          {loadingDs ? (
            <Loader2 size={20} className="animate-spin text-gray-400 mx-auto" />
          ) : datasets?.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-4">No datasets uploaded yet</p>
          ) : (
            <div className="space-y-2">
              {datasets?.map((ds) => (
                <div key={ds.dataset_id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                  <div>
                    <p className="text-sm font-medium text-gray-800 truncate max-w-[200px]">{ds.original_filename}</p>
                    <p className="text-xs text-gray-500">
                      {ds.row_count?.toLocaleString()} rows, {ds.column_count} cols
                    </p>
                  </div>
                  <StatusPill status={ds.status} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Documents */}
        <div className="card p-5">
          <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FileText size={16} className="text-blue-500" /> Documents
          </h2>
          {loadingDocs ? (
            <Loader2 size={20} className="animate-spin text-gray-400 mx-auto" />
          ) : documents?.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-4">No documents uploaded yet</p>
          ) : (
            <div className="space-y-2">
              {documents?.map((doc) => (
                <div key={doc.document_id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                  <div>
                    <p className="text-sm font-medium text-gray-800 truncate max-w-[200px]">{doc.original_filename}</p>
                    <p className="text-xs text-gray-500">
                      {doc.chunk_count} chunks, {doc.page_count} pages
                    </p>
                  </div>
                  <StatusPill status={doc.status} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
