export function StatusBadge({ status, testId }) {
  const s = (status || "").toLowerCase();
  const dotColor = {
    active: "#16A34A",
    cold: "#D97706",
    dead: "#DC2626",
    paid: "#16A34A",
    unpaid: "#64748B",
    overdue: "#DC2626",
  }[s] || "#64748B";
  return (
    <span className={`badge badge-${s}`} data-testid={testId}>
      <span className="dot" style={{ background: dotColor }} />
      {s}
    </span>
  );
}

export function StageBadge({ stage, testId }) {
  const s = (stage || "").toLowerCase();
  return (
    <span className={`badge badge-${s}`} data-testid={testId}>
      {s}
    </span>
  );
}
