import { useState, useEffect } from "react"
import axios from "axios"
import { API } from "../config"

const card = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12 }
const usd = n => "$" + Math.round(n).toLocaleString("en-US")
const label = s => s.replace(/_/g, " ")

function Tile({ title, value, sub }) {
  return (
    <div style={{ ...card, padding: "14px 18px" }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>{title}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: "var(--text-primary)", marginTop: 4 }}>{value}</div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>{sub}</div>
    </div>
  )
}

function Section({ title, hint, children }) {
  return (
    <div>
      <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>{title}</div>
      {hint && <div style={{ fontSize: 12, color: "var(--text-secondary)", margin: "2px 0 8px" }}>{hint}</div>}
      {children}
    </div>
  )
}

export default function SettingsScreen({ businessId }) {
  const [s, setS] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    axios.get(`${API}/api/settings`, { params: { business_id: businessId } })
      .then(r => { if (!cancelled) (r.data.error ? setError("Could not load the settings.") : setS(r.data)) })
      .catch(() => { if (!cancelled) setError("Could not load the settings. Is the backend running?") })
    return () => { cancelled = true }
  }, [businessId])

  if (error) return <div style={{ padding: 24, color: "var(--accent-orange)", fontSize: 13 }}>{error}</div>
  if (!s) return <div style={{ padding: 24, color: "var(--text-secondary)", fontSize: 13 }}>Loading…</div>

  const maxW = Math.max(...Object.values(s.confidence_weights))
  return (
    <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 18, maxWidth: 980 }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>How alerts are decided</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
          Read-only. The rules below are our own estimates, not measured values. They live in <code>config/risk.yaml</code>; the notify threshold and import country are stored per business.
          {!s.has_own_settings && " This business has no settings of its own, so the defaults apply."}
        </div>
      </div>

      <Section title="Your settings" hint="Decide when an alert interrupts you.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 }}>
          <Tile title="Notify at" value={usd(s.notify_threshold_usd)} sub="expected loss at or above this" />
          <Tile title="Watch from" value={usd(s.watch_floor_usd)} sub="below that it is only logged" />
          <Tile title="Always notify above" value={usd(s.rare_event_guard_usd)} sub="a possible loss this big, even if unlikely" />
          <Tile title="You import into" value={s.importing_country} sub="only duties imposed by this country count" />
        </div>
      </Section>

      <Section title="How likely is the loss?" hint="Expected loss = possible loss × likelihood. The likelihood depends on how confident we are in the information.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
          {["high", "medium", "low"].map(b => (
            <Tile key={b} title={`${b} confidence`} value={`${Math.round(s.likelihood_by_band[b] * 100)}%`}
              sub={b === "high" ? `score ${s.band_cutoffs.high} or more` : b === "medium" ? `score ${s.band_cutoffs.medium} to ${s.band_cutoffs.high}` : `score under ${s.band_cutoffs.medium}`} />
          ))}
        </div>
      </Section>

      <Section title="What goes into confidence" hint="Six parts, weighted. A part that does not apply to a signal is left out and the rest are re-weighted.">
        <div style={{ ...card, padding: "12px 16px", display: "grid", gap: 8 }}>
          {Object.entries(s.confidence_weights).sort((a, b) => b[1] - a[1]).map(([k, w]) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 13, color: "var(--text-secondary)" }}>
              <span style={{ width: 150, textTransform: "capitalize" }}>{label(k)}</span>
              <div style={{ flex: 1, height: 8, borderRadius: 4, background: "var(--bg-card-hover)" }}>
                <div style={{ width: `${(w / maxW) * 100}%`, height: "100%", borderRadius: 4, background: "var(--accent-blue)" }} />
              </div>
              <span style={{ width: 40, textAlign: "right", color: "var(--text-primary)" }}>{Math.round(w * 100)}%</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="The money model" hint="Assumptions used to price a delay. A notice with no stated duty rate is never priced.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 }}>
          <Tile title="Delay cost" value={`${s.loss_model.delay_cost_rate_per_day * 100}% a day`} sub="of the shipment's value" />
          <Tile title="Late order loss" value={`${Math.round(s.loss_model.late_order_loss_rate * 100)}%`} sub="of an order's value if it ships late" />
          <Tile title="Heads-up window" value={`${s.horizon_days} days`} sub="how far ahead we look for problems" />
          <Tile title="Tariff window" value={`${s.loss_model.tariff_horizon_days} days`} sub="shipments arriving this soon pay a new tariff" />
        </div>
      </Section>

      <Section title="Assumed delay when a source does not say" hint="Days added to a shipment for each kind of event.">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {Object.entries(s.default_delay_days).map(([k, d]) => (
            <span key={k} style={{ ...card, borderRadius: 999, padding: "5px 12px", fontSize: 12, color: "var(--text-secondary)" }}>
              {label(k)} <b style={{ color: "var(--text-primary)" }}>{d} d</b>
            </span>
          ))}
        </div>
      </Section>
    </div>
  )
}
