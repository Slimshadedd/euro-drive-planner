import { useState } from "react";
import { saveManualFare } from "./api.js";
import { duration, km, money, timeAgo } from "./format.js";
import { Icon } from "./ui.jsx";

const PARTS = [
  ["fuel", "Fuel"],
  ["tolls", "Tolls"],
  ["vignettes", "Vignettes"],
  ["crossings", "Crossings"],
];

function FareBadge({ leg }) {
  if (leg.fare_source === "live") {
    return <span className="badge green" title={leg.fare_detail?.detail}>Live · {timeAgo(leg.fare_detail.fetched_at)}</span>;
  }
  if (leg.fare_source === "manual") return <span className="badge blue">Your quote</span>;
  return <span className="badge orange" title={`Typical ${leg.fare_detail?.season}-season fare`}>Estimate</span>;
}

function QuoteInput({ leg, travelDate, request, currency, onSaved }) {
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState("");
  const [err, setErr] = useState(null);
  if (!open) {
    return (
      <button type="button" className="text-button" onClick={() => setOpen(true)}>
        Enter a quote
      </button>
    );
  }
  return (
    <form
      className="quote"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await saveManualFare({
            route_id: leg.id, date: travelDate, price: +price, currency,
            adults: request.adults, children: request.children, vehicle: request.vehicle,
          });
          setOpen(false);
          onSaved();
        } catch (ex) {
          setErr(ex.message);
        }
      }}
    >
      <input type="number" min="1" step="0.01" value={price} placeholder={`Price in ${currency}`}
        aria-label={`Quoted price in ${currency}`} onChange={(e) => setPrice(e.target.value)} required autoFocus />
      <button type="submit" className="small-button">Save</button>
      <button type="button" className="text-button" onClick={() => setOpen(false)}>Cancel</button>
      {err && <span className="error-text">{err}</span>}
    </form>
  );
}

export default function OptionCard({ option: o, index, selected, onSelect, currency, units, request, travelDate, onRecalc }) {
  const [expanded, setExpanded] = useState(false);
  const total = o.total || 1;
  const crossings = o.legs.filter((l) => l.type === "crossing");

  return (
    <article
      className={`card option ${selected ? "selected" : ""}`}
      onClick={() => onSelect(index)}
      aria-current={selected ? "true" : undefined}
    >
      <header>
        <span className={`select-mark ${selected ? "on" : ""}`} aria-hidden>
          {selected && <Icon name="check" size={13} />}
        </span>
        <div className="titles">
          <h3>{o.title}</h3>
          <p className="secondary">{o.subtitle} · {duration(o.duration_s)} · {km(o.distance_km, units)}</p>
          <div className="badges">
            {o.is_cheapest && <span className="badge solid-green">Cheapest</span>}
            {o.is_fastest && <span className="badge solid-purple">Fastest</span>}
            {crossings.map((l) => (
              <FareBadge key={l.id} leg={l} />
            ))}
            {crossings.some((l) => l.overnight) && <span className="badge gray">Overnight</span>}
          </div>
        </div>
        <div className="price">
          <strong>{money(o.total, currency)}</strong>
          {o.extra_vs_cheapest > 0.5 && <span className="extra">+{money(o.extra_vs_cheapest, currency)}</span>}
        </div>
      </header>

      <div className="bar" aria-hidden>
        {PARTS.map(([k]) =>
          o.breakdown[k] > 0 ? <span key={k} className={`seg ${k}`} style={{ flexGrow: o.breakdown[k] / total }} /> : null
        )}
      </div>
      <ul className="legend">
        {PARTS.map(([k, label]) =>
          o.breakdown[k] > 0 ? (
            <li key={k}>
              <i className={`dot ${k}`} />
              {label} <b>{money(o.breakdown[k], currency)}</b>
            </li>
          ) : null
        )}
      </ul>

      <div className="fuel-compare">
        {["petrol", "diesel"].map((f) => (
          <span key={f} className={request.fuel === f ? "chosen" : ""}>
            {f === "petrol" ? "Petrol" : "Diesel"} {money(o.fuel_compare[f].fuel, currency)}
            <span className="secondary"> → </span>
            <b>{money(o.fuel_compare[f].total, currency)}</b>
          </span>
        ))}
        <span className="secondary">{o.litres} L</span>
      </div>

      <button
        type="button"
        className="disclosure"
        aria-expanded={expanded}
        onClick={(e) => {
          e.stopPropagation();
          setExpanded((x) => !x);
        }}
      >
        {expanded ? "Hide details" : "Journey details"}
        <Icon name="chevron" size={14} />
      </button>

      {expanded && (
        <ol className="legs" onClick={(e) => e.stopPropagation()}>
          {o.legs.map((l, i) =>
            l.type === "road" ? (
              <li key={i} className="leg">
                <span className="leg-icon blue"><Icon name="car" size={16} /></span>
                <div className="leg-body">
                  <div className="leg-head">
                    <span>{l.from} → {l.to}</span>
                    <span className="secondary">{km(l.distance_km, units)} · {duration(l.duration_s)}</span>
                  </div>
                  <table>
                    <thead>
                      <tr><th>Country</th><th>Distance</th><th>Toll roads</th><th>Fuel</th><th>Tolls</th></tr>
                    </thead>
                    <tbody>
                      {l.per_country.map((c) => (
                        <tr key={c.country}>
                          <td>{c.name}</td>
                          <td>{km(c.km, units)}</td>
                          <td>{c.toll_km > 0 ? km(c.toll_km, units) : "–"}</td>
                          <td title={`Petrol ${money(c.petrol_price, currency, 2)}/L · Diesel ${money(c.diesel_price, currency, 2)}/L`}>
                            {money(c.fuel, currency, 2)}
                          </td>
                          <td>{c.toll > 0 ? money(c.toll, currency, 2) : "–"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {l.items.length > 0 && (
                    <ul className="items">
                      {l.items.map((it, k) => (
                        <li key={k}>{it.label} <b>{money(it.amount, currency, 2)}</b></li>
                      ))}
                    </ul>
                  )}
                </div>
              </li>
            ) : (
              <li key={i} className="leg">
                <span className="leg-icon teal"><Icon name={l.kind === "shuttle" ? "train" : "ferry"} size={16} /></span>
                <div className="leg-body">
                  <div className="leg-head">
                    <span>{l.operator}: {l.from} → {l.to}</span>
                    <span className="secondary">{duration(l.duration_min * 60)} + {l.checkin_min} min check-in</span>
                  </div>
                  <p>
                    <b>{money(l.fare, currency, 2)}</b> <FareBadge leg={l} />
                    {l.fare_detail?.departure && <span className="secondary"> · cheapest at {l.fare_detail.departure}</span>}
                    {l.fare_source === "estimate" && <span className="secondary"> · typical {l.fare_detail.season}-season price</span>}
                  </p>
                  {l.fare_source === "live" && l.fare_detail?.detail && (
                    <p className={`footnote ${l.fare_detail.detail.startsWith("No sailing") ? "warn" : ""}`}>{l.fare_detail.detail}</p>
                  )}
                  <p className="actions">
                    <a href={l.booking_url} target="_blank" rel="noreferrer" className="text-button">
                      Book with {l.operator} <Icon name="external" size={13} />
                    </a>
                    <QuoteInput leg={l} travelDate={travelDate} request={request} currency={currency} onSaved={onRecalc} />
                  </p>
                </div>
              </li>
            )
          )}
          {o.vignettes.length > 0 && (
            <li className="leg">
              <span className="leg-icon purple"><Icon name="tag" size={16} /></span>
              <div className="leg-body">
                <div className="leg-head"><span>Vignettes needed</span></div>
                <ul className="items">
                  {o.vignettes.map((v, k) => (
                    <li key={k}>{v.label} <b>{money(v.amount, currency, 2)}</b></li>
                  ))}
                </ul>
              </div>
            </li>
          )}
        </ol>
      )}
    </article>
  );
}
