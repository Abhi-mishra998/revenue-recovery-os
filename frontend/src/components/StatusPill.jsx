export function StatusBadge({ status, testId }) {
  const s = (status || "").toLowerCase();
  const dotColor = {
    active:  "#059669",
    cold:    "#D97706",
    dead:    "#E11D48",
    paid:    "#059669",
    unpaid:  "#71717A",
    overdue: "#E11D48",
  }[s] || "#71717A";
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
