// Fire-and-forget Render warm-up. Render's free tier sleeps after 15 min
// idle; first request after sleep is 15-30 s. Calling this on Login /
// Register page mount means by the time the founder clicks submit, the
// backend is already warm. Saves the worst-case cold-start delay on the
// most user-visible action.

import { api } from "@/lib/api";

let warmed = false;

export function warmupBackend() {
  if (warmed) return;
  warmed = true;
  // No await, no error handling — purely opportunistic.
  api.get("/").catch(() => {});
}
