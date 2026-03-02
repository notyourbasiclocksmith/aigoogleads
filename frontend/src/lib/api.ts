const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApiOptions {
  method?: string;
  body?: any;
  headers?: Record<string, string>;
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
    const { method = "GET", body, headers = {} } = options;
    const token = this.getToken();

    const fetchHeaders: Record<string, string> = {
      "Content-Type": "application/json",
      ...headers,
    };
    if (token) {
      fetchHeaders["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(`${API_URL}${path}`, {
      method,
      headers: fetchHeaders,
      body: body ? JSON.stringify(body) : undefined,
    });

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

  post<T = any>(path: string, body?: any) {
    return this.fetch<T>(path, { method: "POST", body });
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
}

export const api = new ApiClient();
