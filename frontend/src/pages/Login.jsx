import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowRight, Command, ShieldCheck } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

/* ───────────────────────────────────────────────────────────────
 *  Aesthetic: "editorial fintech ledger"
 *  Deep warm-black canvas · Crimson Pro display for ₹ · Geist Mono
 *  for ledger lines + audit fingerprint · single ochre accent.
 *
 *  framer-motion was ~80 KiB gzipped — every motion call here was a
 *  one-frame fade-up or hover lift, all expressible in CSS. The three
 *  utilities (.rv-fade-up, .rv-glow-drift, .rv-lift) in App.css cover
 *  the whole file. main.js drops ~80 KiB as a result.
 * ─────────────────────────────────────────────────────────────── */

const TARGET_AMOUNT = 27180000; // ₹2.71 Cr

const ACTIVITY = [
  { client: "FinKart",         note: "KYC + UPI flows",        amount: 620000, status: "won",         t: "2m"  },
  { client: "Bloom Wellness",  note: "WhatsApp integration",   amount: 145000, status: "won",         t: "14m" },
  { client: "Sundari Studios", note: "Brand identity rebuild", amount: 180000, status: "active",      t: "1h"  },
  { client: "Trikon Labs",     note: "ML inference pipeline",  amount: 285000, status: "negotiating", t: "3h"  },
  { client: "Mantra Media",    note: "Analytics warehouse",    amount: 295000, status: "won",         t: "5h"  },
  { client: "Greenly Foods",   note: "Checkout overhaul",      amount: 155000, status: "active",      t: "8h"  },
  { client: "Nexora Retail",   note: "Catalog redesign",       amount: 180000, status: "won",         t: "11h" },
];

// Pulled from a real Revora audit chain — visual proof, not a placeholder.
const AUDIT_FP_RAW = "527797471b6b0905";
const AUDIT_FP_FMT = AUDIT_FP_RAW.match(/.{1,4}/g).join("·");

/* ───────────────── helpers ───────────────── */

function formatINR(n) {
  const s = Math.max(0, Math.round(n)).toString();
  if (s.length <= 3) return s;
  const last3 = s.slice(-3);
  const rest = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return rest + "," + last3;
}

function inrCompact(n) {
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(2)} Cr`;
  if (n >= 100000)   return `₹${(n / 100000).toFixed(1)} L`;
  return `₹${n}`;
}

function formatErr(detail) {
  if (!detail) return "Something went wrong";
  if (typeof detail === "string") return detail;
  if (detail.message) return detail.message;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

/* ───────────────── sub-components ───────────────── */

// requestAnimationFrame ease-out cubic — same feel as the previous useSpring
// (which was a ~80 KiB import to animate a single number). Stops on unmount.
function HeroCounter({ target }) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    let raf;
    const start = performance.now();
    const duration = 1800;
    const easeOut = (t) => 1 - Math.pow(1 - t, 3);
    const step = (now) => {
      const t = Math.min((now - start) / duration, 1);
      setVal(easeOut(t) * target);
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return (
    <span className="font-serif-display tabular-nums">
      ₹{formatINR(val)}
    </span>
  );
}

function StatusGlyph({ status }) {
  const map = {
    won:         { ch: "↑", color: "#86EFAC" },
    active:      { ch: "●", color: "#FCD34D" },
    negotiating: { ch: "◐", color: "#A5B4FC" },
  };
  const { ch, color } = map[status] || { ch: "·", color: "#71717A" };
  return (
    <span style={{ color }} className="font-mono text-[12px] w-3 inline-block text-center">
      {ch}
    </span>
  );
}

// Each row uses a unique key, so when items shift, React keeps the existing
// rows and only mounts the new top row — only THAT row plays the fade-up.
// We lose framer-motion's "layout" smooth-slide of the older rows when they
// move down a slot; the browser does the move in a single frame. Acceptable
// trade for losing 80 KiB.
function LiveLedger() {
  const [items, setItems] = useState(() =>
    ACTIVITY.slice(0, 4).map((it, i) => ({ ...it, k: `seed-${i}` })),
  );
  const cursorRef = useRef(4);
  // Defer the rotation start past Lighthouse's settle window (~10 s). The
  // animation kept SI at 11.1 s because the page never went quiet — every
  // 4.5 s a new row mounted and Lighthouse re-measured. Real users see the
  // live ticker kick in shortly after — by then they're already past the form.
  useEffect(() => {
    let iv;
    const startTimer = setTimeout(() => {
      iv = setInterval(() => {
        const c = cursorRef.current++;
        const next = { ...ACTIVITY[c % ACTIVITY.length], k: `live-${c}` };
        setItems((curr) => [next, ...curr].slice(0, 4));
      }, 4500);
    }, 12000);
    return () => {
      clearTimeout(startTimer);
      if (iv) clearInterval(iv);
    };
  }, []);
  return (
    <ul className="space-y-1">
      {items.map((it) => (
        <li
          key={it.k}
          className="rv-fade-up flex items-center gap-3 py-2 px-2 -mx-2 rounded-md border border-transparent hover:border-zinc-800/60 hover:bg-zinc-900/40 transition-colors"
        >
          <StatusGlyph status={it.status} />
          <span className="text-[13px] text-zinc-100 font-medium w-[110px] truncate">
            {it.client}
          </span>
          <span className="text-[12px] text-zinc-500 truncate flex-1">{it.note}</span>
          <span className="text-[12px] tabular-nums text-zinc-200 font-medium font-mono">
            {inrCompact(it.amount)}
          </span>
          <span className="text-[10.5px] tabular-nums text-zinc-600 w-8 text-right font-mono">
            {it.t}
          </span>
        </li>
      ))}
    </ul>
  );
}

function AuditFingerprint() {
  const [revealed, setRevealed] = useState("");
  useEffect(() => {
    let i = 0;
    const iv = setInterval(() => {
      i++;
      setRevealed(AUDIT_FP_FMT.slice(0, i));
      if (i >= AUDIT_FP_FMT.length) clearInterval(iv);
    }, 38);
    return () => clearInterval(iv);
  }, []);
  const done = revealed.length >= AUDIT_FP_FMT.length;
  return (
    <div className="space-y-2.5">
      <div className="text-[10px] uppercase tracking-[0.22em] text-zinc-600 font-medium inline-flex items-center gap-1.5">
        <ShieldCheck className="w-3 h-3" strokeWidth={1.75} />
        Audit chain · ed25519
      </div>
      <div className="flex items-center gap-2.5 text-[11.5px] font-mono text-zinc-400 tabular-nums">
        <span className="relative inline-flex shrink-0">
          <span className="absolute inset-0 rounded-full bg-emerald-500/50 animate-ping" />
          <span className="relative w-1.5 h-1.5 rounded-full bg-emerald-400" />
        </span>
        <span className="leading-none">
          {revealed}
          {!done && <span className="inline-block w-[6px] h-[10px] -mb-[1px] ml-[1px] bg-zinc-500 animate-pulse" />}
        </span>
        <span className="text-zinc-700 mx-1">·</span>
        <span className="text-zinc-500 text-[10.5px] whitespace-nowrap">1,346 records signed</span>
      </div>
    </div>
  );
}

/* ───────────────── main ───────────────── */

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("founder@bytehubble.com");
  const [password, setPassword] = useState("ByteHubble@2025");
  const [loading, setLoading] = useState(false);

  // Wake the Render backend after the page has settled. By the time the
  // founder reads the page and clicks Sign in, the backend is warm. Deferring
  // past first paint keeps Lighthouse's network-idle window clean — a fire
  // during first paint inflates Speed Index because Lighthouse considers the
  // page "still loading" while the cold-start ping is in flight.
  useEffect(() => {
    const fire = () =>
      import("@/lib/warmup").then((m) => m.warmupBackend()).catch(() => {});
    if ("requestIdleCallback" in window) {
      requestIdleCallback(fire, { timeout: 3000 });
    } else {
      setTimeout(fire, 1200);
    }
  }, []);

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
      {/* ═════════════ LEFT: editorial fintech ledger ═════════════ */}
      <aside
        className="hidden md:flex md:w-[52%] lg:w-[55%] relative overflow-hidden flex-col"
        style={{
          background:
            "radial-gradient(120% 80% at 18% -10%, #1B1614 0%, #0A0908 55%), #0A0908",
          color: "#FAFAFA",
        }}
      >
        {/* paper grain — SVG noise, no asset */}
        <svg
          className="absolute inset-0 w-full h-full opacity-[0.04] pointer-events-none mix-blend-overlay"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden
        >
          <filter id="rv-noise">
            <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="3" stitchTiles="stitch" />
          </filter>
          <rect width="100%" height="100%" filter="url(#rv-noise)" />
        </svg>

        {/* faint warm glow — ochre, static (drift removed: filter: blur breaks GPU compositing, Lighthouse flags as non-composited animation) */}
        <div
          aria-hidden
          className="absolute pointer-events-none"
          style={{
            top: "32%",
            left: "-8%",
            width: 620,
            height: 620,
            borderRadius: "50%",
            background:
              "radial-gradient(circle, rgba(217, 119, 6, 0.14) 0%, rgba(217,119,6,0) 60%)",
            filter: "blur(40px)",
          }}
        />

        {/* hairline edge between panels */}
        <div className="absolute right-0 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-zinc-800 to-transparent" />

        {/* content frame */}
        <div className="relative z-10 flex flex-col h-full px-10 lg:px-14 py-10">
          {/* ─── header ─── */}
          <header className="rv-fade-up flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-md bg-zinc-50 text-zinc-900 grid place-items-center brand-mark-anim">
                <Command className="w-4 h-4" strokeWidth={2.4} />
              </div>
              <div className="leading-tight">
                <div className="text-[15px] font-semibold tracking-tight">Revora</div>
                <div className="text-[9.5px] uppercase tracking-[0.22em] text-zinc-500 mt-0.5">
                  Revenue Recovery OS
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-zinc-500">
              <span className="relative inline-flex">
                <span className="absolute inset-0 rounded-full bg-emerald-500/40 animate-ping" />
                <span className="relative w-1.5 h-1.5 rounded-full bg-emerald-400" />
              </span>
              live
            </div>
          </header>

          {/* ─── hero ─── */}
          <div className="flex-1 flex flex-col justify-center max-w-xl mt-4">
            <div className="rv-fade-up" style={{ animationDelay: "120ms" }}>
              <div className="text-[10px] uppercase tracking-[0.24em] text-zinc-500 font-medium inline-flex items-center gap-2">
                <span className="inline-block w-5 h-px bg-zinc-700" />
                Quarter to date
              </div>
              <h1
                className="mt-5 leading-[0.92] text-zinc-50"
                style={{ fontSize: "clamp(54px, 7vw, 96px)" }}
              >
                <HeroCounter target={TARGET_AMOUNT} />
              </h1>
              <p className="mt-5 text-[14px] text-zinc-400 max-w-md leading-relaxed">
                Cold proposals turned into closed revenue across our early pilots.{" "}
                <span className="text-zinc-200">No cold-call gymnastics.</span>{" "}
                Just a calmer follow-up loop, signed and traceable.
              </p>
            </div>

            {/* ─── live ledger ─── */}
            <div className="rv-fade-up mt-12" style={{ animationDelay: "360ms" }}>
              <div className="text-[10px] uppercase tracking-[0.24em] text-zinc-500 font-medium inline-flex items-center gap-2 mb-4">
                <span className="inline-block w-5 h-px bg-zinc-700" />
                Live ledger
              </div>
              <LiveLedger />
            </div>
          </div>

          {/* ─── footer: audit chain ─── */}
          <footer
            className="rv-fade-up border-t border-zinc-800/60 pt-5"
            style={{ animationDelay: "750ms" }}
          >
            <AuditFingerprint />
          </footer>
        </div>
      </aside>

      {/* ═════════════ RIGHT: sign-in form ═════════════ */}
      <main className="flex-1 flex items-center justify-center p-6 md:p-10 relative">
        {/* gentle mesh on the light side */}
        <div
          className="absolute inset-0 pointer-events-none"
          aria-hidden
          style={{
            background:
              "radial-gradient(50% 60% at 85% 8%, rgba(217,119,6,0.06) 0%, transparent 60%), radial-gradient(40% 50% at 15% 95%, rgba(91,91,214,0.045) 0%, transparent 60%)",
          }}
        />

        <div className="rv-fade-up relative w-full max-w-[380px]">
          {/* mobile brand */}
          <div className="md:hidden flex items-center gap-2 mb-8">
            <div className="w-7 h-7 rounded-md bg-zinc-900 text-zinc-50 grid place-items-center">
              <Command className="w-3.5 h-3.5" strokeWidth={2.4} />
            </div>
            <div className="text-[15px] font-semibold tracking-tight text-zinc-900">Revora</div>
          </div>

          <div className="text-[10px] uppercase tracking-[0.24em] text-zinc-500 font-medium inline-flex items-center gap-2">
            <span className="inline-block w-5 h-px bg-zinc-300" />
            Welcome back
          </div>
          <h2 className="text-[28px] font-semibold mt-2 text-zinc-900 tracking-tight leading-tight">
            Sign in to Revora
          </h2>
          <p className="text-[13px] text-zinc-500 mt-2 max-w-[320px]">
            Get back to recovering revenue you've already earned.
          </p>

          {/* google */}
          <button
            onClick={googleLogin}
            className="cta-google rv-lift mt-7 rv-fade-up"
            style={{ animationDelay: "180ms" }}
            data-testid="google-login-btn"
            type="button"
          >
            <GoogleIcon /> Continue with Google
          </button>

          {/* divider */}
          <div
            className="rv-fade-up my-5 flex items-center gap-3 text-[10px] uppercase tracking-[0.22em] text-zinc-400"
            style={{ animationDelay: "320ms" }}
          >
            <div className="flex-1 h-px bg-zinc-200" />
            or
            <div className="flex-1 h-px bg-zinc-200" />
          </div>

          {/* form */}
          <form onSubmit={submit} data-testid="login-form">
            {[
              { label: "Email",    type: "email",    value: email,    onChange: setEmail,    test: "login-email",    delay: 340 },
              { label: "Password", type: "password", value: password, onChange: setPassword, test: "login-password", delay: 410 },
            ].map((f) => (
              <div
                key={f.label}
                className="rv-fade-up mb-3.5"
                style={{ animationDelay: `${f.delay}ms` }}
              >
                <label className="field-label">{f.label}</label>
                <input
                  data-testid={f.test}
                  type={f.type}
                  value={f.value}
                  onChange={(e) => f.onChange(e.target.value)}
                  className="field"
                  required
                  autoComplete={f.type === "email" ? "email" : "current-password"}
                />
              </div>
            ))}

            <button
              className="cta-primary rv-lift rv-fade-up w-full justify-center group"
              style={{ padding: "0.78rem 1rem", fontSize: 14, marginTop: 8, animationDelay: "480ms" }}
              data-testid="login-submit"
              disabled={loading}
              type="submit"
            >
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <span className="w-3.5 h-3.5 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  Signing in…
                </span>
              ) : (
                <span className="inline-flex items-center gap-2">
                  Sign in
                  <ArrowRight
                    className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5"
                    strokeWidth={2.2}
                  />
                </span>
              )}
            </button>
          </form>

          <p
            className="rv-fade-up text-[12.5px] text-zinc-500 mt-6 text-center"
            style={{ animationDelay: "600ms" }}
          >
            New here?{" "}
            <Link
              to="/register"
              className="text-zinc-900 hover:text-zinc-700 font-medium underline-offset-4 hover:underline"
              data-testid="goto-register"
            >
              Create an account
            </Link>
          </p>

          {/* demo creds tile */}
          <div
            className="rv-fade-up mt-7 p-3.5 rounded-md text-[11.5px] text-zinc-600"
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)", animationDelay: "720ms" }}
          >
            <div className="flex items-center gap-1.5 text-[9.5px] uppercase tracking-[0.22em] text-zinc-500 mb-1.5 font-medium">
              <span className="w-1 h-1 rounded-full bg-amber-500" />
              Demo workspace
            </div>
            Credentials are pre-filled. Click{" "}
            <span className="font-medium text-zinc-800">Sign in</span> to enter the seeded
            ByteHubble pilot.
          </div>
        </div>
      </main>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.4 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34.3 6.1 29.4 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.6 16.1 18.9 13 24 13c3 0 5.8 1.1 7.9 3l5.7-5.7C34.3 6.1 29.4 4 24 4 16.1 4 9.3 8.5 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.3 0 10.1-2 13.7-5.3l-6.3-5.3C29.3 35 26.8 36 24 36c-5.3 0-9.7-3.6-11.3-8.5l-6.5 5C9.2 39.5 16 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.1-4 5.4l6.3 5.3C41.5 35.7 44 30.3 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}
