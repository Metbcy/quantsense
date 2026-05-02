"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, LogIn, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const { login, register } = useAuth();
  const router = useRouter();

  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setLoading(true);
    try {
      if (mode === "login") {
        await login(username.trim(), password);
      } else {
        await register(username.trim(), password);
      }
      toast.success(mode === "login" ? "Logged in" : "Account created");
      router.push("/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Brand mark */}
        <div className="mb-8 flex flex-col items-center gap-2 text-center">
          <div className="flex items-center gap-1.5">
            <span className="text-lg font-medium tracking-tight text-foreground">
              quantsense
            </span>
            <span className="size-1.5 rounded-full bg-primary" aria-hidden />
          </div>
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Editorial Trading Terminal
          </span>
        </div>

        {/* Card */}
        <div className="rounded-md border border-border bg-card">
          <div className="border-b border-border px-5 py-4">
            <h1 className="text-base font-semibold tracking-tight text-foreground">
              {mode === "login" ? "Sign in" : "Create account"}
            </h1>
            <p className="mt-1 text-xs text-muted-foreground">
              {mode === "login"
                ? "Access your portfolio and research."
                : "Register a new quantsense account."}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 px-5 py-5">
            <div className="space-y-1.5">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="username"
                autoComplete="username"
                className="font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                className="font-mono"
              />
            </div>
            <Button
              type="submit"
              disabled={loading || !username.trim() || !password}
              className="w-full"
            >
              {loading ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" />
              ) : mode === "login" ? (
                <LogIn className="mr-1.5 size-4" />
              ) : (
                <UserPlus className="mr-1.5 size-4" />
              )}
              {mode === "login" ? "Sign in" : "Register"}
            </Button>
          </form>

          <div className="border-t border-border px-5 py-3 text-center text-xs text-muted-foreground">
            {mode === "login" ? (
              <>
                No account?{" "}
                <button
                  onClick={() => setMode("register")}
                  className="font-medium text-primary underline-offset-4 hover:underline"
                >
                  Register
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  onClick={() => setMode("login")}
                  className="font-medium text-primary underline-offset-4 hover:underline"
                >
                  Sign in
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
