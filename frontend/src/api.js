async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  return res.json();
}

export const geocode = (q, signal) => request(`/api/geocode?q=${encodeURIComponent(q)}`, { signal });
export const planTrip = (body) => request("/api/plan", { method: "POST", body: JSON.stringify(body) });
export const saveManualFare = (body) =>
  request("/api/fares/manual", { method: "POST", body: JSON.stringify(body) });
