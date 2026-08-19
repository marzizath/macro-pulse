/**
 * Thin fetch wrapper for the Net Reconciler API.
 * VITE_API_BASE_URL / VITE_APP_SECRET come from frontend/.env (see .env.example).
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const APP_SECRET = import.meta.env.VITE_APP_SECRET || "";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(APP_SECRET ? { Authorization: `Bearer ${APP_SECRET}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${options.method || "GET"} ${path} failed: ${res.status} ${body}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  getSummary: (period = "week") => request(`/summary?period=${period}`),
  getTransactions: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/transactions${qs ? `?${qs}` : ""}`);
  },
  patchTransaction: (id, body) =>
    request(`/transactions/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  getReceivables: (open = true) => request(`/receivables?open=${open}`),
  settleReceivable: (id) => request(`/receivables/${id}/settle`, { method: "POST" }),
  triggerSync: () => request("/sync", { method: "POST" }),
};
