import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

function formatErr(detail) {
  if (!detail) return "Something went wrong";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("founder@bytehubble.com");
  const [password, setPassword] = useState("ByteHubble@2025");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back");
      nav("/");
    } catch (err) {
      toast.error(formatErr(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grain-bg flex">
      {/* Left brand panel */}
      <div className="hidden md:flex md:w-[44%] bg-stone-900 text-amber-50 p-12 flex-col justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-md bg-amber-50 text-stone-900 grid place-items-center font-serif-display text-2xl">R</div>
            <div>
              <div className="font-serif-display text-3xl leading-none">Revora</div>
              <div className="text-[10px] uppercase tracking-[0.28em] text-amber-200/70 mt-1">Revenue Recovery OS</div>
            </div>
          </div>
        </div>
        <div className="space-y-6">
          <h1 className="font-serif-display text-5xl leading-[1.05] text-amber-50">
            The proposals you forgot to chase. <span className="text-amber-300/90">In rupees.</span>
          </h1>
          <p className="text-stone-300 max-w-md">
            Stop losing deals in WhatsApp threads and Excel sheets. Revora shows you exactly what
            went cold, how much ₹ you can still recover, and what to follow up on today.
          </p>
          <div className="text-xs uppercase tracking-[0.22em] text-amber-200/60">
            Built for Indian agencies · Designed with ByteHubble
          </div>
        </div>
        <div className="text-[11px] text-stone-400">© 2026 Revora — Crafted in Bengaluru</div>
      </div>

      {/* Form */}
      <div className="flex-1 flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm" data-testid="login-form">
          <h2 className="font-serif-display text-3xl mb-1">Sign in</h2>
          <p className="text-sm text-stone-500 mb-6">Welcome back. Let's recover some revenue.</p>

          <label className="block mb-1 text-xs uppercase tracking-[0.18em] text-stone-500">Email</label>
          <input
            data-testid="login-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5 mb-4 focus:outline-none focus:border-amber-600 transition"
            required
          />

          <label className="block mb-1 text-xs uppercase tracking-[0.18em] text-stone-500">Password</label>
          <input
            data-testid="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5 mb-6 focus:outline-none focus:border-amber-600 transition"
            required
          />

          <button
            data-testid="login-submit"
            disabled={loading}
            className="cta-primary w-full justify-center disabled:opacity-60"
            type="submit"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>

          <p className="text-xs text-stone-500 mt-6 text-center">
            New here?{" "}
            <Link to="/register" className="text-amber-700 hover:text-amber-800 font-medium" data-testid="goto-register">
              Create an account
            </Link>
          </p>

          <div className="mt-8 p-3 rounded-md border border-stone-200 bg-amber-50/60 text-[11px] text-stone-600">
            <div className="uppercase tracking-[0.18em] text-stone-500 mb-1">Demo account pre-filled</div>
            Click Sign in to enter the seeded ByteHubble workspace.
          </div>
        </form>
      </div>
    </div>
  );
}
