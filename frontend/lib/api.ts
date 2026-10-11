export async function apiRequest(path: string, options: {
  method?: string; body?: unknown; csrf?: string; idempotencyKey?: string;
} = {}) {
  const csrf = options.csrf || (typeof window !== "undefined" ? sessionStorage.getItem("apx_csrf") : null);
  return fetch(`/api${path}`, { method: options.method || "GET", credentials: "same-origin",
    headers: { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      ...(options.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}) },
    ...(options.body ? { body: options.body instanceof FormData ? options.body : JSON.stringify(options.body) } : {}) });
}
