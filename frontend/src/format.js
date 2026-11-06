const SYMBOL = { GBP: "£", EUR: "€" };

export function money(value, currency, decimals = 0) {
  if (value == null || Number.isNaN(value)) return "–";
  const s = Number(value).toLocaleString("en-GB", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${SYMBOL[currency] ?? ""}${s}`;
}

export function duration(seconds) {
  const m = Math.round(seconds / 60);
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return h ? `${h}h ${String(mm).padStart(2, "0")}m` : `${mm}m`;
}

export function km(value, units) {
  if (units === "mi") return `${Math.round(value * 0.621371).toLocaleString("en-GB")} mi`;
  return `${Math.round(value).toLocaleString("en-GB")} km`;
}

export const mpgToL100 = (mpg) => 282.481 / mpg;

export function timeAgo(ts) {
  const mins = Math.round((Date.now() / 1000 - ts) / 60);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  return `${Math.round(mins / 60)} h ago`;
}

export function isoDate(d) {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 10);
}
