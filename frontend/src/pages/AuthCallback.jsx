import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

export default function AuthCallback() {
  const { completeGoogleSession } = useAuth();
  const nav = useNavigate();
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    const hash = window.location.hash || "";
    const m = hash.match(/session_id=([^&]+)/);
    if (!m) {
      nav("/login", { replace: true });
      return;
    }
    const sessionId = decodeURIComponent(m[1]);

    (async () => {
      try {
        await completeGoogleSession(sessionId);
        // Clear the fragment from the URL before navigating
        window.history.replaceState(null, "", window.location.pathname);
        toast.success("Signed in with Google");
        nav("/", { replace: true });
      } catch (e) {
        toast.error("Google sign-in failed. Please try again.");
        nav("/login", { replace: true });
      }
    })();
  }, [completeGoogleSession, nav]);

  return (
    <div className="min-h-screen grid place-items-center text-slate-500" data-testid="auth-callback">
      Signing you in with Google…
    </div>
  );
}
