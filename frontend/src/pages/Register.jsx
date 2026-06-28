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

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", company: "", password: "" });
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

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

  return (
    <div className="min-h-screen grain-bg grid place-items-center p-6">
      <form onSubmit={submit} className="w-full max-w-md revora-card p-8" data-testid="register-form">
        <div className="flex items-center gap-2 mb-6">
          <div className="w-8 h-8 rounded-md bg-stone-900 text-amber-50 grid place-items-center font-serif-display text-xl">R</div>
          <div className="font-serif-display text-2xl">Revora</div>
        </div>
        <h2 className="font-serif-display text-3xl mb-1">Create an account</h2>
        <p className="text-sm text-stone-500 mb-6">Start recovering revenue you've already earned.</p>

        <label className="block mb-1 text-xs uppercase tracking-[0.18em] text-stone-500">Your name</label>
        <input data-testid="register-name" value={form.name} onChange={set("name")} required
          className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5 mb-3" />

        <label className="block mb-1 text-xs uppercase tracking-[0.18em] text-stone-500">Company</label>
        <input data-testid="register-company" value={form.company} onChange={set("company")}
          className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5 mb-3" />

        <label className="block mb-1 text-xs uppercase tracking-[0.18em] text-stone-500">Email</label>
        <input data-testid="register-email" type="email" value={form.email} onChange={set("email")} required
          className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5 mb-3" />

        <label className="block mb-1 text-xs uppercase tracking-[0.18em] text-stone-500">Password</label>
        <input data-testid="register-password" type="password" value={form.password} onChange={set("password")} required minLength={6}
          className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5 mb-6" />

        <button data-testid="register-submit" disabled={loading} className="cta-primary w-full justify-center disabled:opacity-60">
          {loading ? "Creating…" : "Create account"}
        </button>

        <p className="text-xs text-stone-500 mt-6 text-center">
          Already have an account?{" "}
          <Link to="/login" className="text-amber-700 hover:text-amber-800 font-medium" data-testid="goto-login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
