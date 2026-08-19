/**
 * Fetch wrapper for the Aegis API.
 *
 * The JWT lives in memory only (module variable set by AuthContext) — never
 * localStorage. A page refresh logs the investigator out, which is the right
 * trade for a demo credential.
 */

import type {
  ApplicationDetail,
  ApplicationList,
  DriftResponse,
  FeedbackResponse,
  RingInfo,
  SampleId,
  ScoreRequest,
  ScoreResponse,
  SimilarCasesResponse,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the Aegis API. Is the backend running?");
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (body.error === "rate_limit_exceeded") message = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg)
        message = `Invalid input: ${body.detail[0].msg}`;
    } catch {
      /* keep generic message */
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  listApplications: (params: { limit?: number; offset?: number; decision_band?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.set("limit", String(params.limit));
    if (params.offset) q.set("offset", String(params.offset));
    if (params.decision_band) q.set("decision_band", params.decision_band);
    return request<ApplicationList>(`/applications?${q}`);
  },

  getApplication: (id: string) => request<ApplicationDetail>(`/applications/${id}`),
  getRing: (id: string) => request<RingInfo>(`/applications/${id}/ring`),
  getSimilarCases: (id: string) =>
    request<SimilarCasesResponse>(`/applications/${id}/similar-cases`),

  score: (payload: ScoreRequest) =>
    request<ScoreResponse>("/score", { method: "POST", body: JSON.stringify(payload) }),

  submitFeedback: (id: string, verdict: string, notes?: string) =>
    request<FeedbackResponse>(`/applications/${id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ verdict, notes: notes || null }),
    }),

  getDrift: (windowHours = 24) =>
    request<DriftResponse>(`/monitoring/drift?window_hours=${windowHours}`),

  getSampleId: (mismatch: boolean) =>
    request<SampleId>(`/demo/sample-id?mismatch=${mismatch}`),

  /** Fetch a protected ID image as an object URL (img tags can't send JWTs). */
  getIdImageUrl: async (filename: string): Promise<string> => {
    const headers: Record<string, string> = {};
    if (authToken) headers.Authorization = `Bearer ${authToken}`;
    const response = await fetch(`${BASE_URL}/demo/id-image/${filename}`, { headers });
    if (!response.ok) throw new ApiError(response.status, "Document image not found");
    return URL.createObjectURL(await response.blob());
  },
};
