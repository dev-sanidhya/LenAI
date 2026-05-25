import axios from "axios";

const BASE_URL = (import.meta.env.VITE_API_URL as string) || "http://localhost:8000";

// API key is NEVER embedded in the frontend bundle.
// The user provides it once at login; the backend exchanges it for a signed JWT.
// All subsequent requests use the JWT. The raw API key is discarded client-side.
export const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

// Inject Bearer token from in-memory store (not localStorage - no XSS persistence)
let _token: string | null = null;

// Callback the AuthContext registers so it can react to forced logouts
// (e.g. when the interceptor sees a 401 from an expired token).
// Without this, clearing the token would leave isAuthenticated=true and
// the UI would stay mounted, firing repeated failing requests.
let _onUnauthorized: (() => void) | null = null;

export function registerUnauthorizedHandler(handler: (() => void) | null) {
  _onUnauthorized = handler;
}

export function setAuthToken(token: string | null) {
  _token = token;
  if (token) {
    api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common["Authorization"];
  }
}

export function getAuthToken(): string | null {
  return _token;
}

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const message =
      err.response?.data?.detail || err.message || "An unexpected error occurred";
    if (err.response?.status === 401) {
      // Token expired or invalid: clear it AND notify AuthContext so the UI
      // unmounts the authenticated tree and routes back to the login screen.
      setAuthToken(null);
      if (_onUnauthorized) _onUnauthorized();
    }
    return Promise.reject(new Error(message));
  }
);

// --- Auth ---
export const exchangeApiKey = (apiKey: string) =>
  axios.post(`${BASE_URL}/api/v1/auth/token`, { api_key: apiKey });

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
  is_ephemeral?: boolean;
}) => api.post("/query", payload);

export const submitAction = (auditRecordId: string, action: string, comment?: string) =>
  api.post(`/query/${auditRecordId}/action`, { action, comment });

// --- Audit ---
export const listAuditRecords = (limit = 50, offset = 0) =>
  api.get(`/audit?limit=${limit}&offset=${offset}`);

export const getAuditRecord = (id: string) => api.get(`/audit/${id}`);

/**
 * Download audit export via authenticated fetch (not bare <a href>).
 * Browsers do NOT attach custom headers to anchor navigations,
 * so we must use the axios instance which carries the Bearer token.
 */
export async function downloadAuditExport(id: string, format: "json" | "pdf"): Promise<void> {
  const response = await api.get(`/audit/${id}/export/${format}`, {
    responseType: "blob",
  });
  const mimeType = format === "json" ? "application/json" : "application/pdf";
  const blob = new Blob([response.data], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `lenai_audit_${id.slice(0, 8)}.${format}`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

// --- Sessions ---
export const listSessions = () => api.get("/sessions");
export const getSession = (id: string) => api.get(`/sessions/${id}`);
