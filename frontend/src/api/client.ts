import axios from "axios";

const BASE_URL = (import.meta.env.VITE_API_URL as string) || "http://localhost:8000";
const API_KEY = (import.meta.env.VITE_API_KEY as string) || "dev-api-key-change-in-production";

export const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
  },
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const message =
      err.response?.data?.detail || err.message || "An unexpected error occurred";
    return Promise.reject(new Error(message));
  }
);

// --- Ingestion ---
export const uploadCsv = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/ingest/csv", form, { headers: { "Content-Type": "multipart/form-data" } });
};

export const uploadPdf = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/ingest/pdf", form, { headers: { "Content-Type": "multipart/form-data" } });
};

export const getCsvStatus = (datasetId: string) => api.get(`/ingest/status/csv/${datasetId}`);
export const getPdfStatus = (documentId: string) => api.get(`/ingest/status/pdf/${documentId}`);
export const listDatasets = () => api.get("/ingest/datasets");
export const listDocuments = () => api.get("/ingest/documents");
export const updateColumnTags = (datasetId: string, tags: Record<string, string>) =>
  api.patch(`/ingest/csv/${datasetId}/tags`, tags);

// --- Query ---
export const submitQuery = (payload: {
  question: string;
  session_id?: string;
  dataset_ids?: string[];
  document_ids?: string[];
  scenario_assumptions?: Record<string, unknown>;
  scenario_label?: string;
}) => api.post("/query", payload);

export const submitAction = (auditRecordId: string, action: string, comment?: string) =>
  api.post(`/query/${auditRecordId}/action`, { action, comment });

export const compareScenarios = (
  scenarios: Array<{
    question: string;
    session_id?: string;
    dataset_ids?: string[];
    document_ids?: string[];
    scenario_assumptions?: Record<string, unknown>;
    scenario_label?: string;
  }>
) => api.post("/query/scenarios", scenarios);

// --- Audit ---
export const listAuditRecords = (limit = 50, offset = 0) =>
  api.get(`/audit?limit=${limit}&offset=${offset}`);
export const getAuditRecord = (id: string) => api.get(`/audit/${id}`);
export const exportAuditJson = (id: string) =>
  `${BASE_URL}/api/v1/audit/${id}/export/json`;
export const exportAuditPdf = (id: string) =>
  `${BASE_URL}/api/v1/audit/${id}/export/pdf`;

// --- Sessions ---
export const listSessions = () => api.get("/sessions");
export const getSession = (id: string) => api.get(`/sessions/${id}`);
