// Thin fetch wrapper: cookie auth, JSON both ways, errors as thrown messages.
async function req(method, path, body) {
  const res = await fetch(path, {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) throw new Error("401");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export const api = {
  get: (p) => req("GET", p),
  post: (p, b = {}) => req("POST", p, b),
  put: (p, b = {}) => req("PUT", p, b),
};
