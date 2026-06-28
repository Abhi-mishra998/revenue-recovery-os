// Indian rupee formatting: 1,00,000 / 1,50,000 / 1,25,00,000 etc.

const formatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export function inr(n) {
  if (n == null || isNaN(n)) return "₹0";
  return formatter.format(Math.round(Number(n)));
}

export function inrCompact(n) {
  if (n == null || isNaN(n)) return "₹0";
  const v = Number(n);
  const abs = Math.abs(v);
  if (abs >= 1_00_00_000) return `₹${(v / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `₹${(v / 1_00_000).toFixed(2)} L`;
  if (abs >= 1_000) return `₹${(v / 1_000).toFixed(1)} K`;
  return `₹${v.toFixed(0)}`;
}

export function dateShort(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return "—"; }
}

export function dateForInput(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch { return ""; }
}
