import PlaceInput from "./PlaceInput.jsx";
import { mpgToL100 } from "./format.js";
import { Group, Icon, Row, Segmented, Stepper, Switch } from "./ui.jsx";

const VEHICLES = [
  ["car", "Car"],
  ["van", "Van / minibus"],
  ["campervan", "Campervan"],
  ["car_caravan", "Car + caravan"],
];

export default function TripForm({ form, setForm, onSubmit, busy }) {
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const ready = form.origin && form.destination && form.date && (!form.is_return || form.return_date);
  const sym = form.currency === "GBP" ? "£" : "€";

  return (
    <form
      className="trip-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready && !busy) onSubmit();
      }}
    >
      <Group>
        <div className="places">
          <PlaceInput id="from" label="From" icon="start" value={form.origin} onChange={set("origin")} placeholder="Start" />
          <PlaceInput id="to" label="To" icon="end" value={form.destination} onChange={set("destination")} placeholder="Destination" />
          <button
            type="button"
            className="swap"
            title="Swap start and destination"
            aria-label="Swap start and destination"
            onClick={() => setForm((f) => ({ ...f, origin: f.destination, destination: f.origin }))}
          >
            <Icon name="swap" size={16} />
          </button>
        </div>
      </Group>

      <Group title="When">
        <Row label="Return journey" icon="return">
          <Switch label="Return journey" checked={form.is_return} onChange={set("is_return")} />
        </Row>
        <Row label={form.is_return ? "Outbound" : "Date"} htmlFor="date" icon="calendar">
          <input id="date" type="date" className="pill" value={form.date} min={form.minDate}
            onChange={(e) => {
              const d = e.target.value;
              setForm((f) => ({ ...f, date: d, return_date: f.return_date && f.return_date < d ? d : f.return_date }));
            }} />
        </Row>
        {form.is_return && (
          <Row label="Return" htmlFor="return-date" icon="calendar">
            <input id="return-date" type="date" className="pill" value={form.return_date} min={form.date}
              onChange={(e) => set("return_date")(e.target.value)} />
          </Row>
        )}
      </Group>

      <Group title="Travellers & vehicle">
        <Row label={<>Adults <b className="count">{form.adults}</b></>} icon="people">
          <Stepper label="adults" value={form.adults} min={1} max={9} onChange={set("adults")} />
        </Row>
        <Row label={<>Children <b className="count">{form.children}</b></>} icon="people">
          <Stepper label="children" value={form.children} min={0} max={8} onChange={set("children")} />
        </Row>
        <Row label="Vehicle" htmlFor="vehicle" icon="car">
          <select id="vehicle" className="plain" value={form.vehicle} onChange={(e) => set("vehicle")(e.target.value)}>
            {VEHICLES.map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </Row>
        <Row label="Fuel" icon="fuel">
          <Segmented name="Fuel used for the total" value={form.fuel} onChange={set("fuel")}
            options={[["petrol", "Petrol"], ["diesel", "Diesel"]]} size="compact" />
        </Row>
        <Row stacked icon="gauge" label={
          <span className="slider-label">
            Fuel economy
            <span className="value">{form.mpg} mpg <span className="secondary">· {mpgToL100(form.mpg).toFixed(1)} L/100km</span></span>
          </span>
        }>
          <input aria-label="Fuel economy in miles per gallon" type="range" min={15} max={80} step={1}
            value={form.mpg} onChange={(e) => set("mpg")(+e.target.value)}
            style={{ "--p": `${((form.mpg - 15) / 65) * 100}%` }} />
        </Row>
      </Group>

      <Group title="Preferences">
        <Row stacked label="Optimise for" icon="sort">
          <Segmented name="Optimise for" value={form.mode} onChange={set("mode")}
            options={[["cheapest", "Cheapest"], ["balanced", "Balanced"], ["fastest", "Fastest"]]} />
        </Row>
        {form.mode === "balanced" && (
          <Row stacked icon="tag" label={
            <span className="slider-label">Value of your time <span className="value">{sym}{form.value_of_time} / hour</span></span>
          }>
            <input aria-label="Value of your time per hour" type="range" min={0} max={50} step={1}
              value={form.value_of_time} onChange={(e) => set("value_of_time")(+e.target.value)}
              style={{ "--p": `${(form.value_of_time / 50) * 100}%` }} />
          </Row>
        )}
        <Row label="Live fares" icon="bolt">
          <Switch label="Fetch live fares" checked={form.live_fares} onChange={set("live_fares")} />
        </Row>
        <Row label="Avoid tolls" icon="tag">
          <Switch label="Avoid tolls" checked={form.avoid_tolls} onChange={set("avoid_tolls")} />
        </Row>
        <Row label="Currency" icon="tag">
          <Segmented name="Currency" value={form.currency} onChange={set("currency")}
            options={[["GBP", "£ GBP"], ["EUR", "€ EUR"]]} size="compact" />
        </Row>
      </Group>

      <button className="primary" type="submit" disabled={!ready || busy}>
        {busy ? "Finding routes…" : form.is_return ? "Find Return Routes" : "Find Routes"}
      </button>
      {!ready && <p className="hint">Choose a start and destination from the suggestions.</p>}
    </form>
  );
}
