// Use relative URLs in browser (leverages Next.js rewrites to proxy /api/* to backend).
// Only use the explicit backend URL for SSR or when explicitly set.
const API_URL =
  typeof window !== "undefined"
    ? ""
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Pipeline requests (campaign creation) can take 10-20 minutes.
// Default browser fetch has no timeout, so we set a generous one.
const DEFAULT_TIMEOUT_MS = 20 * 60 * 1000; // 20 minutes

interface ApiOptions {
  method?: string;
  body?: any;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  timeoutMs?: number;
}

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      if (typeof window !== "undefined") localStorage.setItem("token", token);
    } else {
      if (typeof window !== "undefined") localStorage.removeItem("token");
    }
  }

  getToken(): string | null {
    if (this.token) return this.token;
    if (typeof window !== "undefined") {
      this.token = localStorage.getItem("token");
    }
    return this.token;
  }

  async fetch<T = any>(path: string, options: ApiOptions = {}): Promise<T> {
    const { method = "GET", body, headers = {}, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
    const token = this.getToken();

    const fetchHeaders: Record<string, string> = {
      "Content-Type": "application/json",
      ...headers,
    };
    if (token) {
      fetchHeaders["Authorization"] = `Bearer ${token}`;
    }

    // Combine user-provided signal (e.g. cancel button) with a timeout signal
    let combinedSignal = signal;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    if (timeoutMs > 0) {
      const timeoutController = new AbortController();
      timeoutId = setTimeout(() => timeoutController.abort(), timeoutMs);
      // If a user signal is provided, abort on either
      if (signal) {
        signal.addEventListener("abort", () => timeoutController.abort());
      }
      combinedSignal = timeoutController.signal;
    }

    let res: Response;
    try {
      res = await fetch(`${API_URL}${path}`, {
        method,
        headers: fetchHeaders,
        body: body ? JSON.stringify(body) : undefined,
        signal: combinedSignal,
      });
    } catch (err: any) {
      if (timeoutId) clearTimeout(timeoutId);
      if (err.name === "AbortError" && signal && !signal.aborted) {
        // The timeout fired, not the user cancel
        throw new Error(
          `Request timed out after ${Math.round(timeoutMs / 60000)} minutes — the pipeline may still be running. Refresh to check results.`
        );
      }
      throw err;
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
    }

    if (res.status === 401) {
      this.setToken(null);
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      throw new Error("Unauthorized");
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    return res.json();
  }

  get<T = any>(path: string) {
    return this.fetch<T>(path);
  }

  post<T = any>(path: string, body?: any, opts?: { signal?: AbortSignal; timeoutMs?: number }) {
    return this.fetch<T>(path, { method: "POST", body, signal: opts?.signal, timeoutMs: opts?.timeoutMs });
  }

  put<T = any>(path: string, body?: any) {
    return this.fetch<T>(path, { method: "PUT", body });
  }

  patch<T = any>(path: string, body?: any) {
    return this.fetch<T>(path, { method: "PATCH", body });
  }

  delete<T = any>(path: string) {
    return this.fetch<T>(path, { method: "DELETE" });
  }

  /**
   * Stream SSE events from a POST endpoint.
   * Calls onEvent for each parsed SSE data line.
   */
  async streamPost(
    path: string,
    body: any,
    onEvent: (event: any) => void,
  ): Promise<void> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    if (res.status === 401) {
      this.setToken(null);
      if (typeof window !== "undefined") window.location.href = "/login";
      throw new Error("Unauthorized");
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No readable stream");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data: ")) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            onEvent(data);
          } catch {
            // skip malformed lines
          }
        }
      }
    }

    // Process remaining buffer
    if (buffer.trim().startsWith("data: ")) {
      try {
        onEvent(JSON.parse(buffer.trim().slice(6)));
      } catch {
        // skip
      }
    }
  }
}

export const api = new ApiClient();
