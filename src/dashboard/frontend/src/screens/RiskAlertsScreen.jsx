import { useState, useEffect, useCallback, useRef } from "react"
import axios from "axios"
import { API } from "../config"

const LEVELS = [
  { id: "", label: "All" },
  { id: "notify", label: "Notify" },
  { id: "watch", label: "Watch" },
  { id: "log", label: "Log" },
]
const LEVEL_STYLE = {
  notify: { color: "var(--accent-red)", text: "Notify" },
  watch: { color: "var(--accent-yellow)", text: "Watch" },
  log: { color: "var(--text-secondary)", text: "Log" },
}
const BAND_COLOR = { high: "var(--accent-green)", medium: "var(--accent-yellow)", low: "var(--accent-orange)" }

const usd = n => (n == null ? "-" : "$" + Math.round(n).toLocaleString("en-US"))

function ago(iso) {
  if (!iso) return "never"
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 90) return "just now"
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

function Pill({ color, children, title }) {
  return (
    <span title={title} style={{
      fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, whiteSpace: "nowrap",
      color, background: `color-mix(in srgb, ${color} 14%, transparent)`,
      border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
    }}>{children}</span>
  )
}

const card = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12 }

// ── Pipeline status + manual trigger ────────────────────────────────────────────────────────────────────
function PipelineBar({ onFinished }) {
  const [status, setStatus] = useState(null)
  const [msg, setMsg] = useState(null)
  const wasRunning = useRef(false)

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/pipeline/status`, { params: { limit: 1 } })
      setStatus(data)
      if (wasRunning.current && !data.running) onFinished()
      wasRunning.current = data.running
    } catch { setStatus(null) }
  }, [onFinished])

  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t) }, [load])
  // while a run is going, look every 3 s; otherwise every minute
  useEffect(() => {
    const t = setInterval(load, status?.running ? 3000 : 60000)
    return () => clearInterval(t)
  }, [load, status?.running])

  async function run() {
    setMsg(null)
    try {
      await axios.post(`${API}/api/pipeline/run`)
      wasRunning.current = true
      setStatus(s => ({ ...(s || { recent_runs: [] }), running: true }))
    } catch (e) {
      setMsg(e.response?.status === 409 ? "A run is already in progress." : "Could not start a run.")
    }
  }

  const last = status?.recent_runs?.[0]
  const ok = last?.status === "ok"
  return (
    <div style={{ ...card, padding: "10px 14px", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
      <div style={{ fontSize: 13, color: "var(--text-secondary)", flex: 1, minWidth: 220 }}>
        {status?.running
          ? "Analysis running now (reading news, scoring risk, judging)…"
          : last
            ? <>Last analysis <b style={{ color: "var(--text-primary)" }}>{ago(last.finished_at || last.started_at)}</b> · {last.trigger} · {" "}
                <span style={{ color: ok ? "var(--accent-green)" : "var(--accent-red)" }}>{ok ? "all steps ok" : last.status}</span></>
            : status ? "No analysis has run yet." : "Pipeline status unavailable."}
        {msg && <span style={{ color: "var(--accent-orange)", marginLeft: 8 }}>{msg}</span>}
      </div>
      <button onClick={run} disabled={!status || status.running} style={{
        background: "var(--accent-blue)", border: "none", borderRadius: 8, color: "#fff", fontWeight: 600, fontSize: 13,
        padding: "7px 16px", cursor: !status || status.running ? "not-allowed" : "pointer", opacity: !status || status.running ? 0.5 : 1,
      }}>{status?.running ? "Running…" : "Run analysis now"}</button>
    </div>
  )
}

// ── One alert ───────────────────────────────────────────────────────────────────────────────────────────
function Detail({ id }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    axios.get(`${API}/api/risk/alerts/${id}`).then(r => (r.data.error ? setErr(true) : setD(r.data))).catch(() => setErr(true))
  }, [id])
  if (err) return <div style={{ color: "var(--accent-orange)", fontSize: 13 }}>Could not load the details.</div>
  if (!d) return <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>Loading…</div>

  const h = { fontSize: 11, fontWeight: 700, letterSpacing: 0.6, color: "var(--text-muted)", textTransform: "uppercase", margin: "12px 0 4px" }
  const li = { fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.55 }
  const lc = d.loss_components || {}
  return (
    <div>
      <div style={h}>How the loss was worked out</div>
      {(d.explanation || []).map((x, i) => <div key={i} style={li}>• {x}</div>)}
      {Object.keys(lc).length > 0 && (
        <div style={{ ...li, marginTop: 4 }}>Possible loss parts: {Object.entries(lc).map(([k, v]) => `${k.replace(/_/g, " ")} ${usd(v)}`).join(" · ")}</div>
      )}
      <div style={h}>Why this confidence</div>
      {(d.confidence_reasons || []).map((x, i) => <div key={i} style={li}>• {x}</div>)}
      {d.assumptions?.length > 0 && <><div style={h}>Assumptions</div>{d.assumptions.map((x, i) => <div key={i} style={li}>• {x}</div>)}</>}
      <div style={h}>Affected</div>
      <div style={li}>
        {d.affected_shipments?.length || 0} shipment(s): {(d.affected_shipments || []).join(", ") || "none"}<br />
        {d.affected_suppliers?.length || 0} supplier(s): {(d.affected_suppliers || []).map(s => `${s.supplier_name} (${s.country})`).join(", ") || "none"}
      </div>
      {d.judge_reasoning && <><div style={h}>Judge ({d.judge_model})</div><div style={li}>{d.judge_reasoning}</div></>}
      <div style={{ ...li, marginTop: 10, color: "var(--text-muted)", fontSize: 11 }}>
        alert id {d.alert_id} · source {d.source} · first seen {ago(d.first_seen)} · event {d.event_start || "?"} to {d.event_end || "?"}
      </div>
    </div>
  )
}

function AlertCard({ a, onAck }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const lv = LEVEL_STYLE[a.level] || LEVEL_STYLE.log

  async function ack(e) {
    e.stopPropagation()
    setBusy(true)
    try { await axios.post(`${API}/api/risk/alerts/${a.alert_id}/acknowledge`); onAck() } catch { setBusy(false) }
  }

  return (
    <div style={{ ...card, borderLeft: `3px solid ${lv.color}`, overflow: "hidden" }}>
      <div onClick={() => setOpen(o => !o)} style={{ padding: "12px 14px", cursor: "pointer" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
          <Pill color={lv.color}>{lv.text}</Pill>
          <Pill color={BAND_COLOR[a.confidence_band] || "var(--text-secondary)"} title={`confidence score ${a.confidence_score}`}>
            {a.confidence_band} confidence
          </Pill>
          {a.stockout_risk && <Pill color="var(--accent-red)" title="Stock would run out before replacement stock could arrive">stockout risk</Pill>}
          <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: "auto" }}>{a.source} · {ago(a.last_seen)}</span>
        </div>
        <div style={{ color: "var(--text-primary)", fontSize: 14, fontWeight: 600, lineHeight: 1.4 }}>{a.title}</div>
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 8, fontSize: 13, color: "var(--text-secondary)" }}>
          <span>Expected loss <b style={{ color: "var(--text-primary)" }}>{usd(a.expected_loss_usd)}</b></span>
          <span>Exposure {usd(a.exposure_usd)}</span>
          {a.act_by && <span>Act by <b style={{ color: "var(--text-primary)" }}>{a.act_by}</b></span>}
        </div>
        {a.action && <div style={{ marginTop: 8, fontSize: 13, color: "var(--text-primary)" }}>➜ {a.action}</div>}
      </div>
      {open && (
        <div style={{ padding: "0 14px 14px", borderTop: "1px solid var(--border)" }}>
          <Detail id={a.alert_id} />
          <button onClick={ack} disabled={busy} style={{
            marginTop: 12, background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: 8,
            color: "var(--text-primary)", fontSize: 12, padding: "6px 12px", cursor: busy ? "not-allowed" : "pointer",
          }}>{busy ? "Saving…" : "Acknowledge"}</button>
        </div>
      )}
    </div>
  )
}

// ── Screen ──────────────────────────────────────────────────────────────────────────────────────────────
export default function RiskAlertsScreen({ businessId }) {
  const [level, setLevel] = useState("")
  const [alerts, setAlerts] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/risk/alerts`, { params: { business_id: businessId, level: level || undefined, limit: 100 } })
      if (data.error) throw new Error(data.error)
      setAlerts(data.alerts); setError(null)
    } catch { setError("Could not load alerts. Is the backend running?") }
  }, [businessId, level])

  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t) }, [load])

  const counts = (alerts || []).reduce((m, a) => ({ ...m, [a.level]: (m[a.level] || 0) + 1 }), {})
  const total = (alerts || []).reduce((s, a) => s + (a.expected_loss_usd || 0), 0)

  return (
    <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 14, maxWidth: 980 }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>Risk Alerts</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
          Sorted by importance. <b>Notify</b> = act now, <b>Watch</b> = keep an eye on it, <b>Log</b> = for the record. Click an alert to see how it was worked out.
        </div>
      </div>

      <PipelineBar onFinished={load} />

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        {LEVELS.map(l => (
          <button key={l.id} onClick={() => setLevel(l.id)} style={{
            background: level === l.id ? "var(--accent-blue)" : "var(--bg-card)", color: level === l.id ? "#fff" : "var(--text-secondary)",
            border: "1px solid var(--border)", borderRadius: 999, padding: "5px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
          }}>{l.label}</button>
        ))}
        {alerts && (
          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-secondary)" }}>
            {alerts.length} alert{alerts.length === 1 ? "" : "s"}
            {" "}({["notify", "watch", "log"].filter(k => counts[k]).map(k => `${counts[k]} ${k}`).join(", ") || "none"}) · combined expected loss {usd(total)}
          </span>
        )}
      </div>

      {error && <div style={{ ...card, padding: 14, color: "var(--accent-orange)", fontSize: 13 }}>{error}</div>}
      {!error && alerts === null && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>Loading…</div>}
      {alerts && alerts.length === 0 && !error && (
        <div style={{ ...card, padding: 18, color: "var(--text-secondary)", fontSize: 14 }}>No open alerts{level ? ` at the ${level} level` : ""}. Nothing needs your attention.</div>
      )}
      {(alerts || []).map(a => <AlertCard key={a.alert_id} a={a} onAck={load} />)}
    </div>
  )
}
