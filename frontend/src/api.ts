export const API = "";

export async function apiGet<T>(url: string): Promise<T> {
  const response = await fetch(`${API}${url}`);
  if (!response.ok) {
    let msg = `Request failed: ${response.status}`;
    try {
      const errData = await response.json();
      if (errData.detail) msg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
    } catch {
      // ignore malformed error responses
    }
    throw new Error(msg);
  }
  return response.json();
}

export async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(`${API}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    let msg = `Request failed: ${response.status}`;
    try {
      const errData = await response.json();
      if (errData.detail) msg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
    } catch {
      // ignore malformed error responses
    }
    throw new Error(msg);
  }
  return response.json();
}

export async function apiPostFile<T>(url: string, file: File): Promise<T> {
  const response = await fetch(`${API}${url}`, {
    method: "POST",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file
  });
  if (!response.ok) {
    let msg = `Request failed: ${response.status}`;
    try {
      const errData = await response.json();
      if (errData.detail) msg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
    } catch {
      // ignore malformed error responses
    }
    throw new Error(msg);
  }
  return response.json();
}

export async function apiDelete<T>(url: string): Promise<T> {
  const response = await fetch(`${API}${url}`, { method: "DELETE" });
  if (!response.ok) {
    let msg = `Request failed: ${response.status}`;
    try {
      const errData = await response.json();
      if (errData.detail) msg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
    } catch {
      // ignore malformed error responses
    }
    throw new Error(msg);
  }
  return response.json();
}
