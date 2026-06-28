import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, ShieldAlert, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

export default function Settings() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [exporting, setExporting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const exportData = async () => {
    setExporting(true);
    try {
      const { data } = await api.get("/me/data");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `revora-data-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Your data has been downloaded.");
    } catch (e) {
      toast.error("Could not export your data. " + (e.response?.data?.detail || ""));
    } finally {
      setExporting(false);
    }
  };

  const deleteAccount = async () => {
    setDeleting(true);
    try {
      await api.delete("/me");
      toast.success("Account deleted. Goodbye.");
      // Force a clean local logout — the token belongs to a user that no longer exists.
      await logout();
      nav("/login", { replace: true });
    } catch (e) {
      toast.error("Could not delete your account. " + (e.response?.data?.detail || ""));
      setDeleting(false);
    }
  };

  return (
    <div className="p-6 md:p-10 max-w-[800px] mx-auto" data-testid="settings-page">
      <header className="mb-8">
        <div className="text-[11px] uppercase tracking-[0.08em] text-zinc-500 font-medium">Account</div>
        <h1 className="text-[28px] md:text-[32px] font-semibold mt-1 text-zinc-900 tracking-tight">Settings</h1>
        <p className="text-[13.5px] text-zinc-500 mt-1.5">
          Signed in as <span className="text-zinc-900 font-medium">{user?.email}</span>.
        </p>
      </header>

      {/* Export */}
      <section className="revora-card p-5 md:p-6 mb-4" data-testid="settings-export">
        <div className="flex items-start gap-3">
          <span className="w-9 h-9 rounded-md bg-sky-50 border border-sky-100 text-sky-700 grid place-items-center">
            <Download className="w-4 h-4" strokeWidth={1.75} />
          </span>
          <div className="flex-1">
            <h2 className="text-base font-semibold text-zinc-900">Export your data</h2>
            <p className="text-[13px] text-zinc-500 mt-1">
              Download a JSON file with every client, proposal, invoice, activity, AI draft, event,
              and derived memory record stored under your account. Includes the timestamps and
              prompt/route refs for every generation.
            </p>
            <button
              onClick={exportData}
              disabled={exporting}
              className="cta-primary mt-4"
              data-testid="settings-export-btn"
            >
              <Download className="w-4 h-4" />
              {exporting ? "Preparing…" : "Download my data (JSON)"}
            </button>
          </div>
        </div>
      </section>

      {/* Delete */}
      <section className="revora-card p-5 md:p-6 border-red-100" data-testid="settings-delete" style={{ borderColor: "#FEE2E2" }}>
        <div className="flex items-start gap-3">
          <span className="w-9 h-9 rounded-md bg-red-50 border border-red-100 text-red-700 grid place-items-center">
            <ShieldAlert className="w-4 h-4" strokeWidth={1.75} />
          </span>
          <div className="flex-1">
            <h2 className="text-base font-semibold text-zinc-900">Delete account</h2>
            <p className="text-[13px] text-zinc-500 mt-1">
              Removes your account and <span className="font-medium text-zinc-800">every record we
              store about you</span> — clients, proposals, invoices, activities, AI drafts,
              events, memory. This action is logged in the tamper-evident audit chain and
              cannot be undone.
            </p>

            {!confirmDelete ? (
              <button
                onClick={() => setConfirmDelete(true)}
                className="cta-danger mt-4"
                data-testid="settings-delete-btn"
              >
                <Trash2 className="w-4 h-4" /> Delete my account
              </button>
            ) : (
              <div className="mt-4 p-3 rounded-md border border-red-200 bg-red-50" data-testid="settings-delete-confirm">
                <div className="text-sm font-medium text-red-900">Are you sure? This is permanent.</div>
                <div className="text-[12px] text-red-800 mt-1">
                  Export your data first if you want a copy.
                </div>
                <div className="flex items-center gap-2 mt-3">
                  <button
                    onClick={deleteAccount}
                    disabled={deleting}
                    className="cta-danger text-sm"
                    data-testid="settings-delete-confirm-btn"
                  >
                    {deleting ? "Deleting…" : "Yes, delete everything"}
                  </button>
                  <button
                    onClick={() => setConfirmDelete(false)}
                    disabled={deleting}
                    className="cta-ghost text-sm"
                    data-testid="settings-delete-cancel"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
