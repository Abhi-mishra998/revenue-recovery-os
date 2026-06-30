import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { warmupBackend } from "@/lib/warmup";

function formatErr(detail) {
  if (!detail) return "Something went wrong";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [loading, setLoading] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  // Wake Render the moment the form mounts — by the time the user fills it
  // out and clicks submit, the backend is warm (no cold-start delay).
  useEffect(() => { warmupBackend(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await register(form);
      toast.success("Account created");
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
    <div className="min-h-screen bg-slate-50 grid place-items-center p-6">
      <div className="w-full max-w-md revora-card p-8" data-testid="register-page">
        <div className="flex items-center gap-2 mb-6">
          <div className="w-8 h-8 rounded-md bg-indigo-700 text-white grid place-items-center font-bold text-lg">R</div>
          <div className="text-xl font-semibold">Revora</div>
        </div>
        <h2 className="text-3xl font-semibold mb-1 text-slate-900">Create account</h2>
        <p className="text-sm text-slate-500 mb-6">Start recovering revenue you&apos;ve already earned.</p>

        <button onClick={googleLogin} className="cta-google" data-testid="google-register-btn">Continue with Google</button>

        <div className="my-5 flex items-center gap-3 text-xs text-slate-400">
          <div className="flex-1 h-px bg-slate-200" /> OR <div className="flex-1 h-px bg-slate-200" />
        </div>

        <form onSubmit={submit} data-testid="register-form">
          <label className="field-label">Your name</label>
          <input data-testid="register-name" value={form.name} onChange={set("name")} required className="field mb-3" />
          <label className="field-label">Email</label>
          <input data-testid="register-email" type="email" value={form.email} onChange={set("email")} required className="field mb-3" />
          <label className="field-label">Password</label>
          <input data-testid="register-password" type="password" value={form.password} onChange={set("password")} required minLength={6} className="field mb-6" />
          <button data-testid="register-submit" disabled={loading} className="cta-primary w-full justify-center">
            {loading ? "Creating…" : "Create account"}
          </button>
        </form>

        <p className="text-xs text-slate-500 mt-6 text-center">
          Already have an account?{" "}
          <Link to="/login" className="text-indigo-700 hover:text-indigo-800 font-medium" data-testid="goto-login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
