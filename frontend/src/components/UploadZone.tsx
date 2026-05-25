import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, Table2, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { uploadCsv, uploadPdf, getCsvStatus, getPdfStatus } from "../api/client";

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
        setUploads((prev) =>
          prev.map((u) => (u.id === id ? { ...u, status } : u))
        );
        if (status === "ready" || status === "failed") {
          clearInterval(interval);
          if (status === "ready") onUploaded?.();
        }
      } catch {
        clearInterval(interval);
      }
    }, 2000);
  };

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
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
        const newUpload: UploadedFile = {
          name: file.name,
          type: isCsv ? "csv" : "pdf",
          id,
          status: res.data.status === "already_exists" ? "ready" : "queued",
        };
        setUploads((prev) => [newUpload, ...prev]);
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
  }, [onUploaded]);

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
    if (status === "ready") return <CheckCircle2 size={16} className="text-green-500" />;
    if (status === "failed") return <XCircle size={16} className="text-red-500" />;
    return <Loader2 size={16} className="text-blue-500 animate-spin" />;
  };

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={clsx(
          "border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors",
          isDragActive ? "border-brand-500 bg-brand-50" : "border-gray-300 hover:border-brand-400 hover:bg-gray-50"
        )}
      >
        <input {...getInputProps()} />
        <Upload size={32} className="mx-auto mb-3 text-gray-400" />
        <p className="text-gray-700 font-medium">Drop files here or click to browse</p>
        <p className="text-gray-500 text-sm mt-1">
          Supports CSV, Excel (.xlsx, .xls), and PDF up to 50MB
        </p>
      </div>

      {uploads.length > 0 && (
        <div className="space-y-2">
          {uploads.map((u) => (
            <div key={u.id} className="flex items-center gap-3 p-3 card px-4">
              {u.type === "pdf" ? (
                <FileText size={18} className="text-red-400 shrink-0" />
              ) : (
                <Table2 size={18} className="text-green-500 shrink-0" />
              )}
              <span className="text-sm text-gray-700 flex-1 truncate">{u.name}</span>
              <span className={clsx("text-xs font-medium",
                u.status === "ready" ? "text-green-600" :
                u.status === "failed" ? "text-red-600" :
                "text-blue-600"
              )}>
                {u.status}
              </span>
              {statusIcon(u.status)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
