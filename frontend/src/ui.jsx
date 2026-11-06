/* Small iOS-style controls: Switch, Stepper, Segmented, grouped List rows, and line icons. */

export function Switch({ id, checked, onChange, label }) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`switch ${checked ? "on" : ""}`}
      onClick={() => onChange(!checked)}
    >
      <span className="knob" />
    </button>
  );
}

export function Stepper({ value, min, max, onChange, label }) {
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button type="button" aria-label={`Fewer ${label}`} disabled={value <= min} onClick={() => onChange(value - 1)}>
        <Icon name="minus" />
      </button>
      <span className="sep" aria-hidden />
      <button type="button" aria-label={`More ${label}`} disabled={value >= max} onClick={() => onChange(value + 1)}>
        <Icon name="plus" />
      </button>
    </div>
  );
}

/** Segmented control with a sliding thumb. options: [[value, label], ...] */
export function Segmented({ name, value, options, onChange, size }) {
  const i = Math.max(0, options.findIndex(([v]) => v === value));
  return (
    <div
      className={`segmented ${size ?? ""}`}
      role="radiogroup"
      aria-label={name}
      style={{ "--n": options.length, "--i": i }}
    >
      <span className="thumb" aria-hidden />
      {options.map(([v, l]) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={v === value}
          className={v === value ? "on" : ""}
          onClick={() => onChange(v)}
        >
          {l}
        </button>
      ))}
    </div>
  );
}

export function Group({ title, footer, children }) {
  return (
    <section className="group">
      {title && <h2 className="group-title">{title}</h2>}
      <div className="group-body">{children}</div>
      {footer && <p className="group-footer">{footer}</p>}
    </section>
  );
}

export function Row({ label, htmlFor, children, stacked, icon }) {
  return (
    <div className={`row ${stacked ? "stacked" : ""}`}>
      {icon && <span className={`row-icon ${icon}`}><Icon name={icon} /></span>}
      {label && (htmlFor ? <label htmlFor={htmlFor} className="row-label">{label}</label> : <span className="row-label">{label}</span>)}
      <div className="row-control">{children}</div>
    </div>
  );
}

const PATHS = {
  car: "M5 17h14M6.5 17v1.5M17.5 17v1.5M4 13.5l1.6-4.3A2 2 0 0 1 7.5 8h9a2 2 0 0 1 1.9 1.2l1.6 4.3M4 13.5V17h16v-3.5M4 13.5h16M7.5 15h.01M16.5 15h.01",
  ferry: "M3 17c1.5 1 3 1 4.5 0s3-1 4.5 0 3 1 4.5 0 3-1 4.5 0M5 14l-1-4h16l-1 4M7 10V7h10v3M10 7V5h4v2",
  train: "M7 4h10a2 2 0 0 1 2 2v8a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V6a2 2 0 0 1 2-2zM5 11h14M9 14.5h.01M15 14.5h.01M8 17l-2 3M16 17l2 3",
  swap: "M7 4v16M7 4L4 7M7 4l3 3M17 20V4M17 20l-3-3M17 20l3-3",
  check: "M5 12.5l4.5 4.5L19 7.5",
  chevron: "M9 6l6 6-6 6",
  minus: "M6 12h12",
  plus: "M12 6v12M6 12h12",
  pin: "M12 21s-6-5.3-6-11a6 6 0 1 1 12 0c0 5.7-6 11-6 11zM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  calendar: "M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zM4 10h16M8 4v4M16 4v4",
  people: "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3.5 19a5.5 5.5 0 0 1 11 0M16 11a2.5 2.5 0 1 0 0-5M17 14a4.5 4.5 0 0 1 3.5 5",
  fuel: "M5 20V5a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v15M4 20h11M5 10h9M14 8l3 2v7a1.5 1.5 0 0 0 3 0V9l-3-3",
  gauge: "M4.5 17a8 8 0 1 1 15 0M12 13l3.5-4M12 13h.01",
  bolt: "M13 3L5 13h6l-1 8 8-10h-6l1-8z",
  tag: "M3 12V4h8l9 9-8 8-9-9zM7.5 8h.01",
  sort: "M4 7h11M4 12h8M4 17h5M18 6v13M18 19l-3-3M18 19l3-3",
  return: "M4 9h12a4 4 0 0 1 0 8H8M4 9l4-4M4 9l4 4",
  external: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
  warning: "M12 4l9 16H3l9-16zM12 10v4M12 17h.01",
};

export function Icon({ name, size = 18 }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}
