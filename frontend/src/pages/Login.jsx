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

  const googleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* Brand panel */}
      <div className="hidden md:flex md:w-[44%] bg-indigo-700 text-white p-12 flex-col justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-md bg-white text-indigo-700 grid place-items-center font-bold text-xl">R</div>
          <div>
            <div className="text-2xl font-semibold leading-none">Revora</div>
            <div className="text-[10px] uppercase tracking-[0.28em] text-indigo-200 mt-1">Revenue Recovery OS</div>
          </div>
        </div>
        <div className="space-y-6 max-w-md">
          <h1 className="text-4xl font-semibold leading-[1.15]">
            See every rupee that&apos;s slipping through your follow-ups.
          </h1>
          <p className="text-indigo-100">
            Revora is a calm operator cockpit for B2B service businesses. Track proposals,
            invoices, and clients in one place — built for Indian teams, in ₹.
          </p>
          <div className="flex items-center gap-2 text-xs text-indigo-200">
            <span className="dot bg-teal-400" /> Built for Indian agencies · Designed with ByteHubble
          </div>
        </div>
        <div className="text-xs text-indigo-300">© 2026 Revora · Crafted in Bengaluru</div>
      </div>

      {/* Form */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <h2 className="text-3xl font-semibold mb-1 text-slate-900">Sign in</h2>
          <p className="text-sm text-slate-500 mb-6">Welcome back. Let&apos;s get back to recovering revenue.</p>

          <button onClick={googleLogin} className="cta-google" data-testid="google-login-btn">
            <GoogleIcon />
            Continue with Google
          </button>

          <div className="my-5 flex items-center gap-3 text-xs text-slate-400">
            <div className="flex-1 h-px bg-slate-200" /> OR <div className="flex-1 h-px bg-slate-200" />
          </div>

          <form onSubmit={submit} data-testid="login-form">
            <label className="field-label">Email</label>
            <input
              data-testid="login-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="field mb-4"
              required
            />
            <label className="field-label">Password</label>
            <input
              data-testid="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field mb-6"
              required
            />
            <button
              data-testid="login-submit"
              disabled={loading}
              className="cta-primary w-full justify-center"
              type="submit"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="text-xs text-slate-500 mt-6 text-center">
            New here?{" "}
            <Link to="/register" className="text-indigo-700 hover:text-indigo-800 font-medium" data-testid="goto-register">
              Create an account
            </Link>
          </p>

          <div className="mt-8 p-3 rounded-md border border-slate-200 bg-slate-50 text-[11px] text-slate-600">
            <div className="uppercase tracking-[0.18em] text-slate-500 mb-1">Demo account pre-filled</div>
            Click Sign in to enter the seeded ByteHubble workspace.
          </div>
        </div>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.4 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34.3 6.1 29.4 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/>
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.6 16.1 18.9 13 24 13c3 0 5.8 1.1 7.9 3l5.7-5.7C34.3 6.1 29.4 4 24 4 16.1 4 9.3 8.5 6.3 14.7z"/>
      <path fill="#4CAF50" d="M24 44c5.3 0 10.1-2 13.7-5.3l-6.3-5.3C29.3 35 26.8 36 24 36c-5.3 0-9.7-3.6-11.3-8.5l-6.5 5C9.2 39.5 16 44 24 44z"/>
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.1-4 5.4l6.3 5.3C41.5 35.7 44 30.3 44 24c0-1.3-.1-2.4-.4-3.5z"/>
    </svg>
  );
}
