import { useEffect, useRef, useState } from "react";
import { geocode } from "./api.js";

/** Text box with OpenStreetMap place suggestions. Calls onChange({lat, lon, label}). */
export default function PlaceInput({ id, label, icon, value, onChange, placeholder }) {
  const [text, setText] = useState(value?.label ?? "");
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const typed = useRef(false);

  useEffect(() => {
    if (value) setText(value.label); // parent picked/swapped a place; typing clears value without wiping text
  }, [value]);

  useEffect(() => {
    if (!typed.current || text.trim().length < 2) return;
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await geocode(text.trim(), ctrl.signal);
        setItems(res);
        setOpen(true);
        setActive(-1);
      } catch {
        /* aborted or offline */
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [text]);

  function pick(item) {
    typed.current = false;
    setText(item.label);
    setOpen(false);
    onChange({ lat: item.lat, lon: item.lon, label: item.label, short: item.short });
  }

  function onKeyDown(e) {
    if (!open || !items.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      pick(items[Math.max(active, 0)]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="place">
      <span className={`place-dot ${icon}`} aria-hidden />
      <label htmlFor={id} className="sr-only">{label}</label>
      <input
        id={id}
        type="text"
        autoComplete="off"
        spellCheck={false}
        value={text}
        placeholder={placeholder}
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        onChange={(e) => {
          typed.current = true;
          setText(e.target.value);
          if (value) onChange(null);
        }}
        onKeyDown={onKeyDown}
        onFocus={(e) => {
          e.target.select();
          if (items.length && !value) setOpen(true);
        }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {loading && <span className="spinner small" aria-hidden />}
      {open && items.length > 0 && (
        <ul className="suggestions" id={`${id}-list`} role="listbox">
          {items.map((it, i) => (
            <li
              key={`${it.lat},${it.lon},${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(it);
              }}
            >
              <strong>{it.short}</strong>
              <span>{it.label.replace(`${it.short}, `, "")}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
