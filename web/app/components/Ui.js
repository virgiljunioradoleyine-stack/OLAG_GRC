import { IconWarn } from "./Icons";

export function Severity({ value, children }) {
  const v = value || "NO_DATA";
  return (
    <span className={`sev sev-${v}`}>
      {children || v.replace("_", " ")}
    </span>
  );
}

export function Kpi({ label, value, unit, sub, icon, tint = "var(--accent)" }) {
  return (
    <div className="kpi">
      <span className="kpi-icon"
            style={{ background: `color-mix(in srgb, ${tint} 14%, transparent)`, color: tint }}>
        {icon}
      </span>
      <span style={{ minWidth: 0 }}>
        <span className="kpi-label">{label}</span>
        <div className="kpi-value">
          {value ?? "—"}
          {unit && value != null && <span className="unit">{unit}</span>}
        </div>
        {sub && <div className="kpi-sub">{sub}</div>}
      </span>
    </div>
  );
}

export function Panel({ title, sub, actions, children, bodyStyle }) {
  return (
    <section className="panel">
      {(title || actions) && (
        <header className="panel-head">
          <div>
            {title && <div className="panel-title">{title}</div>}
            {sub && <div className="panel-sub">{sub}</div>}
          </div>
          {actions}
        </header>
      )}
      <div className="panel-body" style={bodyStyle}>{children}</div>
    </section>
  );
}

export function Note({ children }) {
  return (
    <div className="note">
      <IconWarn style={{ flex: "0 0 18px", marginTop: 1 }} />
      <div>{children}</div>
    </div>
  );
}

export function Empty({ children }) {
  return <p className="empty">{children}</p>;
}

/** Renders the indicator with its name, never as NTU. */
export function Indicator({ value, digits = 3 }) {
  if (value == null) return <>—</>;
  return <>{value >= 0 ? "+" : ""}{Number(value).toFixed(digits)}</>;
}
