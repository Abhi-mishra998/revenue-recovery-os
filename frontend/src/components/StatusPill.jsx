export function StatusPill({ status, testId }) {
  const s = (status || "").toLowerCase();
  const cls = `pill pill-${s}`;
  const dotColor = {
    active: "#16A34A",
    cold: "#EA580C",
    dead: "#78716C",
    won: "#0284C7",
    lost: "#DC2626",
    paid: "#16A34A",
    due: "#D97706",
    overdue: "#EA580C",
    critical: "#DC2626",
  }[s] || "#78716C";

  return (
    <span className={cls} data-testid={testId}>
      <span className="dot" style={{ background: dotColor }} />
      {s}
    </span>
  );
}
