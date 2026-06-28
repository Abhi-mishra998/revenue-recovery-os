import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { Command, ShieldCheck, Zap } from "lucide-react";

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
    <div className="min-h-screen flex" style={{ background: "var(--bg)" }}>
      {/* Brand panel — Vercel-black, restrained */}
      <div className="hidden md:flex md:w-[44%] p-12 flex-col justify-between relative overflow-hidden" style={{ background: "#09090B", color: "#FAFAFA" }}>
        {/* subtle grid texture */}
        <div className="absolute inset-0 opacity-[0.05] pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.5) 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />
        {/* Ambient glow */}
        <div className="ambient-glow" />
        <div className="relative">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-md bg-white text-zinc-900 grid place-items-center brand-mark-anim">
              <Command className="w-4 h-4" strokeWidth={2.4} />
            </div>
            <div>
              <div className="text-[18px] font-semibold leading-none">Revora</div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-zinc-400 mt-1">Revenue OS</div>
            </div>
          </div>
        </div>

        <div className="space-y-7 max-w-md relative">
          <h1 className="text-[34px] leading-[1.15] font-semibold tracking-tight text-white">
            The operating system for revenue you&apos;ve already earned.
          </h1>
          <p className="text-zinc-400 text-[14px] leading-relaxed">
            Track proposals, invoices, and follow-ups in one calm cockpit.
            Built for Indian B2B service businesses who measure success in ₹ recovered, not Excel rows.
          </p>
          <div className="grid grid-cols-1 gap-3 pt-2">
            <FeatureRow icon={Zap} title="Live revenue-at-risk" copy="Auto-status flags cold and dead pipeline before they slip away." />
            <FeatureRow icon={ShieldCheck} title="Per-user data isolation" copy="JWT + optional Google login. Your workspace, your data only." />
          </div>
        </div>

        <div className="text-[11px] text-zinc-500 relative">© 2026 Revora · Crafted in Bengaluru</div>
      </div>

      {/* Form */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-[360px]">
          <h2 className="text-[26px] font-semibold mb-1 text-zinc-900 tracking-tight">Sign in</h2>
          <p className="text-[13.5px] text-zinc-500 mb-7">Welcome back. Let&apos;s get back to recovering revenue.</p>

          <button onClick={googleLogin} className="cta-google" data-testid="google-login-btn">
            <GoogleIcon /> Continue with Google
          </button>

          <div className="my-5 flex items-center gap-3 text-[11px] uppercase tracking-[0.12em] text-zinc-400">
            <div className="flex-1 h-px bg-zinc-200" /> Or with email <div className="flex-1 h-px bg-zinc-200" />
          </div>

          <form onSubmit={submit} data-testid="login-form">
            <label className="field-label">Email</label>
            <input
              data-testid="login-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="field mb-3.5"
              required
            />
            <label className="field-label">Password</label>
            <input
              data-testid="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field mb-5"
              required
            />
            <button
              data-testid="login-submit"
              disabled={loading}
              className="cta-primary w-full justify-center"
              style={{ padding: "0.7rem 0.85rem", fontSize: 14 }}
              type="submit"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="text-[12.5px] text-zinc-500 mt-6 text-center">
            New here?{" "}
            <Link to="/register" className="text-zinc-900 hover:text-zinc-700 font-medium underline-offset-4 hover:underline" data-testid="goto-register">
              Create an account
            </Link>
          </p>

          <div className="mt-7 p-3 rounded-md text-[11.5px] text-zinc-500" style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500 mb-1 font-medium">Demo account pre-filled</div>
            Click Sign in to enter the seeded ByteHubble workspace.
          </div>
        </div>
      </div>
    </div>
  );
}

function FeatureRow({ icon: Icon, title, copy }) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-md grid place-items-center shrink-0" style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.08)" }}>
        <Icon className="w-4 h-4 text-white" strokeWidth={1.75} />
      </div>
      <div>
        <div className="text-[13.5px] font-medium text-white">{title}</div>
        <div className="text-[12.5px] text-zinc-400 mt-0.5">{copy}</div>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.4 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34.3 6.1 29.4 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/>
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.6 16.1 18.9 13 24 13c3 0 5.8 1.1 7.9 3l5.7-5.7C34.3 6.1 29.4 4 24 4 16.1 4 9.3 8.5 6.3 14.7z"/>
      <path fill="#4CAF50" d="M24 44c5.3 0 10.1-2 13.7-5.3l-6.3-5.3C29.3 35 26.8 36 24 36c-5.3 0-9.7-3.6-11.3-8.5l-6.5 5C9.2 39.5 16 44 24 44z"/>
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.1-4 5.4l6.3 5.3C41.5 35.7 44 30.3 44 24c0-1.3-.1-2.4-.4-3.5z"/>
    </svg>
  );
}
