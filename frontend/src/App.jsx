import { useEffect, useRef, useState } from "react";
import { planTrip } from "./api.js";
import { duration, isoDate, money } from "./format.js";
import OptionCard from "./OptionCard.jsx";
import RouteMap from "./RouteMap.jsx";
import TripForm from "./TripForm.jsx";
import { Icon, Segmented } from "./ui.jsx";

const STORE_KEY = "edp.form.v2";
const today = new Date();
const addDays = (iso, n) => isoDate(new Date(new Date(iso + "T12:00:00").getTime() + n * 86400000));
const defaultDate = isoDate(new Date(today.getTime() + 21 * 86400000));

const DEFAULTS = {
  origin: null,
  destination: null,
  date: defaultDate,
  is_return: false,
  return_date: addDays(defaultDate, 7),
  adults: 2,
  children: 0,
  vehicle: "car",
  fuel: "petrol",
  mpg: 45,
  mode: "cheapest",
  value_of_time: 10,
  currency: "GBP",
  avoid_tolls: false,
  live_fares: true,
};

function loadForm() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || localStorage.getItem("edp.form.v1") || "null");
    if (saved) {
      const f = { ...DEFAULTS, ...saved, minDate: isoDate(today) };
      if (f.date < isoDate(today)) f.date = defaultDate;
      if (!f.return_date || f.return_date < f.date) f.return_date = addDays(f.date, 7);
      return f;
    }
  } catch {
    /* storage unavailable */
  }
  return { ...DEFAULTS, minDate: isoDate(today) };
}

const fmtDay = (iso) =>
  new Date(iso + "T12:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });

export default function App() {
  const [form, setForm] = useState(loadForm);
  const [result, setResult] = useState(null);
  const [request, setRequest] = useState(null);
  const [dir, setDir] = useState("out");
  const [selected, setSelected] = useState({ out: 0, back: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [units, setUnits] = useState("mi");
  const started = useRef(0);
  const [elapsed, setElapsed] = useState(0);
  const resultsRef = useRef(null);

  useEffect(() => {
    try {
      const { minDate, ...rest } = form;
      localStorage.setItem(STORE_KEY, JSON.stringify(rest));
    } catch {
      /* ignore */
    }
  }, [form]);

  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setElapsed(Math.round((Date.now() - started.current) / 1000)), 500);
    return () => clearInterval(t);
  }, [busy]);

  async function run(body = null) {
    const req = body ?? {
      origin: form.origin,
      destination: form.destination,
      date: form.date,
      return_date: form.is_return ? form.return_date : null,
      adults: form.adults,
      children: form.children,
      vehicle: form.vehicle,
      fuel: form.fuel,
      mpg: form.mpg,
      mode: form.mode,
      value_of_time: form.value_of_time,
      currency: form.currency,
      avoid_tolls: form.avoid_tolls,
      live_fares: form.live_fares,
    };
    setBusy(true);
    setError(null);
    started.current = Date.now();
    setElapsed(0);
    try {
      const res = await planTrip(req);
      setResult(res);
      setRequest(req);
      if (!body) {
        setSelected({ out: 0, back: 0 });
        setDir("out");
      }
      requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const currency = result?.currency ?? form.currency;
  const plans = result ? { out: result, back: result.return_plan } : {};
  const active = plans[dir] ?? plans.out;
  const isReturn = !!result?.return_plan;
  const pick = (d) => plans[d]?.options?.[selected[d]];
  const outPick = pick("out");
  const backPick = pick("back");
  const roundTotal = isReturn && outPick && backPick ? outPick.total + backPick.total : null;
  const ends = request
    ? dir === "back"
      ? [request.destination, request.origin]
      : [request.origin, request.destination]
    : [form.origin, form.destination];

  return (
    <div className="app">
      <RouteMap
        options={active?.options}
        selected={selected[dir]}
        origin={ends[0]}
        destination={ends[1]}
        onSelect={(i) => setSelected((s) => ({ ...s, [dir]: i }))}
      />

      <aside className="sheet">
        <div className="sheet-scroll">
          <header className="large-title">
            <h1>Drive Planner</h1>
            <p className="secondary">Cheapest ways to drive from the UK to Europe, with live ferry and Le Shuttle fares.</p>
          </header>

          <TripForm form={form} setForm={setForm} onSubmit={() => run()} busy={busy} />

          <section className="results" ref={resultsRef} aria-live="polite">
            {busy && (
              <div className="card status">
                <span className="spinner" aria-hidden />
                <div>
                  <b>Finding routes… {elapsed}s</b>
                  <p className="secondary">
                    {form.live_fares
                      ? `Checking every crossing${form.is_return ? " in both directions" : ""} and fetching live fares. This can take up to a minute.`
                      : "Comparing every crossing."}
                  </p>
                </div>
              </div>
            )}
            {error && (
              <div className="card banner red">
                <Icon name="warning" /> <span>Couldn't plan this trip. {error}</span>
              </div>
            )}

            {result && !busy && (
              <>
                {isReturn && (
                  <div className="card round-trip">
                    <div className="rt-head">
                      <span className="secondary">Round trip</span>
                      <strong>{roundTotal != null ? money(roundTotal, currency) : "–"}</strong>
                    </div>
                    {[["out", outPick, result.date], ["back", backPick, result.return_plan.date]].map(([d, p, date]) => (
                      <button key={d} type="button" className={`rt-row ${dir === d ? "on" : ""}`} onClick={() => setDir(d)}>
                        <span className="rt-dir">{d === "out" ? "Out" : "Back"}<span className="secondary">{fmtDay(date)}</span></span>
                        <span className="rt-route">{p ? `${p.title} · ${p.subtitle}` : "No route"}</span>
                        <span className="rt-price">{p ? money(p.total, currency) : "–"}</span>
                        <Icon name="chevron" size={14} />
                      </button>
                    ))}
                    {outPick && backPick && (
                      <p className="footnote">{duration(outPick.duration_s)} out · {duration(backPick.duration_s)} back. Tap a route below to change your choice for each direction.</p>
                    )}
                  </div>
                )}

                <div className="results-head">
                  {isReturn ? (
                    <Segmented name="Direction" value={dir} onChange={setDir}
                      options={[["out", `Out · ${fmtDay(result.date)}`], ["back", `Back · ${fmtDay(result.return_plan.date)}`]]} />
                  ) : (
                    <h2 className="section-title">{active.options.length} best of {active.candidates_considered} routes</h2>
                  )}
                  <Segmented name="Units" value={units} onChange={setUnits} options={[["mi", "mi"], ["km", "km"]]} size="mini" />
                </div>

                {active.warnings?.map((w, i) => (
                  <p key={i} className="banner orange"><Icon name="warning" size={16} /> <span>{w}</span></p>
                ))}
                {active.options.length === 0 && <p className="secondary">No route found.</p>}
                {active.options.map((o, i) => (
                  <OptionCard
                    key={`${dir}-${o.title}-${o.subtitle}`}
                    option={o}
                    index={i}
                    selected={i === selected[dir]}
                    onSelect={(idx) => setSelected((s) => ({ ...s, [dir]: idx }))}
                    currency={currency}
                    units={units}
                    request={request}
                    travelDate={active.date}
                    onRecalc={() => run({ ...request, live_fares: false })}
                  />
                ))}
                <p className="footnote">
                  Fuel prices, tolls and estimated fares are approximate and editable in <code>backend/app/data</code>.
                  Live fares are cached for 6 hours. Always confirm the price with the operator before booking.
                </p>
              </>
            )}
          </section>
        </div>
      </aside>
    </div>
  );
}
