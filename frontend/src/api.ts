const TOKEN_KEY = "ppai_dashboard_jwt";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      clearToken();
    }
    const body = await response.text();
    throw new ApiError(response.status, body || response.statusText);
  }

  return (await response.json()) as T;
}

export interface TraceEvent {
  seq: number;
  event_name: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface RagTrace {
  message_id: number;
  source: string;
  prompt: string;
  rag_debug: { max_score: number; retrieved: unknown[] } | null;
  rag_trace_id: string | null;
  timing: Record<string, number> | null;
  events: TraceEvent[];
}

export interface MessageSummary {
  id: number;
  created_at: string;
  user_id: number;
  source: string;
  prompt: string;
  context_used: boolean;
}

export interface MessageListResponse {
  items: MessageSummary[];
  total: number;
}

export interface DocumentSummary {
  id: number;
  source: string;
  filename: string | null;
  chunk_count: number;
  status: string;
  created_at: string;
}

export interface DocumentListResponse {
  items: DocumentSummary[];
  total: number;
}

export interface ChunkInfo {
  chunk_id: string;
  text: string;
  metadata: Record<string, unknown>;
}

export interface DocumentDetail {
  document: DocumentSummary;
  embedding_model: string;
  collection: string;
  chunks: ChunkInfo[];
}

export async function exchangeOtt(ott: string): Promise<string> {
  const response = await fetch("/api/v1/auth/sso", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ott }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}

export function listMessages(params: { source?: string; limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams();
  if (params.source) search.set("source", params.source);
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  const query = search.toString();
  return request<MessageListResponse>(`/admin/messages${query ? `?${query}` : ""}`);
}

export function getRagTrace(messageId: number) {
  return request<RagTrace>(`/admin/rag_trace/${messageId}`);
}

export function listDocuments(params: { source?: string; q?: string } = {}) {
  const search = new URLSearchParams();
  if (params.source) search.set("source", params.source);
  if (params.q) search.set("q", params.q);
  const query = search.toString();
  return request<DocumentListResponse>(`/admin/documents${query ? `?${query}` : ""}`);
}

export function getDocumentDetail(documentId: number) {
  return request<DocumentDetail>(`/admin/documents/${documentId}`);
}

export interface AuditLogSummary {
  id: number;
  created_at: string;
  user_id: number;
  module: string;
  decision: string;
  status: string;
  command_text: string;
  detail: Record<string, unknown> | null;
}

export interface AuditLogListResponse {
  items: AuditLogSummary[];
  total: number;
}

export function listAuditLog(params: { module?: string; statusFilter?: string } = {}) {
  const search = new URLSearchParams();
  if (params.module) search.set("module", params.module);
  if (params.statusFilter) search.set("status_filter", params.statusFilter);
  const query = search.toString();
  return request<AuditLogListResponse>(`/admin/audit${query ? `?${query}` : ""}`);
}
