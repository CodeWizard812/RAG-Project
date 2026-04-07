// frontend/app/page.tsx
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { login, register, setToken, getToken } from "@/lib/api";

type FormMode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode,     setMode]    = useState<FormMode>("login");
  const [username, setUsername]= useState("");
  const [password, setPassword]= useState("");
  const [email,    setEmail]   = useState("");
  const [error,    setError]   = useState("");
  const [success,  setSuccess] = useState("");
  const [loading,  setLoading] = useState(false);

  useEffect(() => {
    if (getToken()) router.replace("/chat");
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setSuccess(""); setLoading(true);
    try {
      if (mode === "register") {
        await register(username, password, email);
        setSuccess("Account created! You can now sign in.");
        setMode("login");
        setPassword("");
      } else {
        const data = await login(username, password);
        setToken(data.access);
        router.replace("/chat");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 px-4">
      <div className="bg-white border border-gray-200 rounded-xl p-8 w-full max-w-sm">
        <h1 className="text-lg font-semibold text-gray-900 mb-1">
          Financial Intelligence Agent
        </h1>
        <p className="text-sm text-gray-500 mb-6">
          {mode === "login" ? "Sign in to continue" : "Create an account"}
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
            autoComplete="username"
          />

          {mode === "register" && (
            <input
              type="email"
              placeholder="Email (optional)"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoComplete="email"
            />
          )}

          <input
            type="password"
            placeholder={mode === "register" ? "Password (min 8 characters)" : "Password"}
            value={password}
            onChange={e => setPassword(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
            autoComplete={mode === "register" ? "new-password" : "current-password"}
          />
          {error && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
          {success && (
            <p className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
              {success}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading
              ? mode === "login" ? "Signing in…" : "Creating account…"
              : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        {/* Toggle mode */}
        <p className="text-xs text-gray-400 text-center mt-4">
          {mode === "login" ? (
            <>No account?{" "}
              <button onClick={() => { setMode("register"); setError(""); setSuccess(""); }}
                className="text-blue-600 hover:underline">Register</button></>
          ) : (
            <>Already have an account?{" "}
              <button onClick={() => { setMode("login"); setError(""); setSuccess(""); }}
                className="text-blue-600 hover:underline">Sign in</button></>
          )}
        </p>
      </div>
    </div>
  );
}