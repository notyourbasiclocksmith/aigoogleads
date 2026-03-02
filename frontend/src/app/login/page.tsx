"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [fullName, setFullName] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "register") {
        await api.post("/api/auth/register", { email, password, full_name: fullName });
      }
      const data = await api.post("/api/auth/login", { email, password });
      api.setToken(data.access_token);
      if (data.tenants && data.tenants.length > 0) {
        localStorage.setItem("tenant_id", data.tenants[0].tenant_id);
        const selectData = await api.post("/api/auth/select-tenant", {
          tenant_id: data.tenants[0].tenant_id,
        });
        api.setToken(selectData.access_token);
        router.push("/dashboard");
      } else {
        router.push("/onboarding");
      }
    } catch (err: any) {
      setError(err.message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <div className="w-12 h-12 rounded-xl bg-blue-500 flex items-center justify-center font-bold text-white text-xl">
              IA
            </div>
          </div>
          <h1 className="text-3xl font-bold text-white">Ignite Ads AI</h1>
          <p className="text-blue-200 mt-2">AI-Powered Google Ads Marketing Worker</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{mode === "login" ? "Sign In" : "Create Account"}</CardTitle>
            <CardDescription>
              {mode === "login"
                ? "Enter your credentials to access your account"
                : "Create a new account to get started"}
            </CardDescription>
          </CardHeader>
          <form onSubmit={handleSubmit}>
            <CardContent className="space-y-4">
              {mode === "register" && (
                <div className="space-y-2">
                  <label className="text-sm font-medium">Full Name</label>
                  <Input
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="John Smith"
                    required
                  />
                </div>
              )}
              <div className="space-y-2">
                <label className="text-sm font-medium">Email</label>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Password</label>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
            </CardContent>
            <CardFooter className="flex flex-col gap-3">
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Please wait..." : mode === "login" ? "Sign In" : "Create Account"}
              </Button>
              <button
                type="button"
                onClick={() => setMode(mode === "login" ? "register" : "login")}
                className="text-sm text-muted-foreground hover:text-primary transition-colors"
              >
                {mode === "login" ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
              </button>
            </CardFooter>
          </form>
        </Card>
      </div>
    </div>
  );
}
