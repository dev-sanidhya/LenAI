import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { CheckCircle2, FileText, Loader2, Table2, UploadCloud, XCircle } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { getCsvStatus, getPdfStatus, uploadCsv, uploadPdf } from "../api/client";

interface UploadedFile {
  name: string;
  type: "csv" | "pdf";
  id: string;
  status: "queued" | "processing" | "ready" | "failed";
}

export default function UploadZone({ onUploaded }: { onUploaded?: () => void }) {
  const [uploads, setUploads] = useState<UploadedFile[]>([]);

  const pollStatus = (id: string, type: "csv" | "pdf") => {
    const fn = type === "csv" ? getCsvStatus : getPdfStatus;
    const interval = setInterval(async () => {
      try {
        const res = await fn(id);
        const status = res.data.status;
        setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, status } : u)));
        if (status === "ready" || status === "failed") {
          clearInterval(interval);
          if (status === "ready") onUploaded?.();
        }
      } catch {
        clearInterval(interval);
      }
    }, 2000);
  };

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      for (const file of acceptedFiles) {
        const ext = file.name.split(".").pop()?.toLowerCase() || "";
        const isCsv = ["csv", "xlsx", "xls"].includes(ext);
        const isPdf = ext === "pdf";
        if (!isCsv && !isPdf) {
          toast.error(`Unsupported file type: ${ext}`);
          continue;
        }

        try {
          const res = isCsv ? await uploadCsv(file) : await uploadPdf(file);
          const id = isCsv ? res.data.dataset_id : res.data.document_id;
          const status = res.data.status === "already_exists" ? "ready" : "queued";
          setUploads((prev) => [{ name: file.name, type: isCsv ? "csv" : "pdf", id, status }, ...prev]);

          if (res.data.status === "already_exists") {
            toast.success(`${file.name} already processed`);
            onUploaded?.();
          } else {
            toast.success(`${file.name} queued for processing`);
            pollStatus(id, isCsv ? "csv" : "pdf");
          }
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err);
          toast.error(`Upload failed: ${msg}`);
        }
      }
    },
    [onUploaded]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
      "application/pdf": [".pdf"],
    },
    maxSize: 50 * 1024 * 1024,
  });

  const statusIcon = (status: UploadedFile["status"]) => {
    if (status === "ready") return <CheckCircle2 size={16} className="text-emerald-300" />;
    if (status === "failed") return <XCircle size={16} className="text-rose-300" />;
    return <Loader2 size={16} className="animate-spin text-sky-300" />;
  };

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={clsx(
          "rounded-[28px] border border-dashed p-8 text-center transition-all",
          isDragActive
            ? "border-sky-300/50 bg-sky-400/10 shadow-[0_0_0_1px_rgba(91,181,255,0.18)]"
            : "border-white/10 bg-white/[0.02] hover:border-sky-400/30 hover:bg-white/[0.04]"
        )}
      >
        <input {...getInputProps()} />
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-3xl bg-white/[0.04] text-sky-200">
          <UploadCloud size={28} />
        </div>
        <p className="text-lg font-semibold text-white">Drop source files or click to browse</p>
        <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 body-muted">
          Supports CSV, Excel, and PDF up to 50MB. Structured files become tenant-scoped query tables. PDFs are
          extracted, chunked, embedded, and indexed for retrieval.
        </p>
      </div>

      {uploads.length > 0 && (
        <div className="grid gap-3">
          {uploads.map((upload) => (
            <div key={upload.id} className="data-table-row">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/[0.04]">
                  {upload.type === "pdf" ? (
                    <FileText size={18} className="text-rose-300" />
                  ) : (
                    <Table2 size={18} className="text-emerald-300" />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-white">{upload.name}</div>
                  <div className="mt-1 text-xs uppercase tracking-[0.18em] body-muted">
                    {upload.type === "pdf" ? "document ingest" : "dataset ingest"}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={clsx(
                    "text-xs font-semibold uppercase tracking-[0.18em]",
                    upload.status === "ready"
                      ? "text-emerald-200"
                      : upload.status === "failed"
                        ? "text-rose-200"
                        : "text-sky-200"
                  )}
                >
                  {upload.status}
                </span>
                {statusIcon(upload.status)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
