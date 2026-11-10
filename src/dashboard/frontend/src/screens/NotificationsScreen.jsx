import { useState, useEffect, useCallback } from "react"
import axios from "axios"
import { API } from "../config"

const PAGE = 20
const card = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12 }
const usd = n => "$" + Math.round(n).toLocaleString("en-US")
const BAND_COLOR = { high: "var(--accent-green)", medium: "var(--accent-yellow)", low: "var(--accent-orange)" }
const STATUS_TEXT = { open: "still open", acknowledged: "acknowledged", resolved: "resolved" }

function dayLabel(iso) {
  const d = new Date(iso)
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const that = new Date(d); that.setHours(0, 0, 0, 0)
  const diff = Math.round((today - that) / 86400000)
  if (diff === 0) return "Today"
  if (diff === 1) return "Yesterday"
  return d.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric", year: "numeric" })
}

function Pill({ color, children, title }) {
  return (
    <span title={title} style={{
      fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, whiteSpace: "nowrap", color,
      background: `color-mix(in srgb, ${color} 14%, transparent)`, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
    }}>{children}</span>
  )
}

function Row({ n, onOpen }) {
  const time = new Date(n.notified_at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
  return (
    <div style={{ ...card, borderLeft: "3px solid var(--accent-red)", padding: "12px 14px" }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 62 }}>{time}</span>
        <Pill color="var(--accent-red)">Notify</Pill>
        <Pill color={BAND_COLOR[n.confidence_band] || "var(--text-secondary)"}>{n.confidence_band} confidence</Pill>
        {n.stockout_risk && <Pill color="var(--accent-red)" title="Stock would run out before replacement stock could arrive">stockout risk</Pill>}
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }} title="Why ChainGuard decided to notify">· {n.reason}</span>
        {n.alert_status && <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-muted)" }}>alert {STATUS_TEXT[n.alert_status] || n.alert_status}</span>}
      </div>
      <div style={{ color: "var(--text-primary)", fontSize: 14, fontWeight: 600, lineHeight: 1.4 }}>{n.title}</div>
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 6, fontSize: 13, color: "var(--text-secondary)" }}>
        <span>Expected loss <b style={{ color: "var(--text-primary)" }}>{usd(n.expected_loss_usd)}</b></span>
        {n.act_by && <span>Act by <b style={{ color: "var(--text-primary)" }}>{String(n.act_by).slice(0, 10)}</b></span>}
        {n.source && <span style={{ color: "var(--text-muted)" }}>source {n.source}</span>}
      </div>
      {n.action && <div style={{ marginTop: 6, fontSize: 13, color: "var(--text-primary)" }}>➜ {n.action}</div>}
      <button onClick={onOpen} style={{ marginTop: 8, background: "none", border: "none", color: "var(--accent-blue)", fontSize: 12, cursor: "pointer", padding: 0 }}>
        Open Risk Alerts →
      </button>
    </div>
  )
}

export default function NotificationsScreen({ businessId, onNavigate }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [more, setMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  const fetchPage = useCallback(async (offset) => {
    const { data } = await axios.get(`${API}/api/notifications`, { params: { business_id: businessId, limit: PAGE, offset } })
    if (data.error) throw new Error(data.error)
    return data.notifications
  }, [businessId])

  useEffect(() => {
    let cancelled = false
    fetchPage(0)
      .then(r => { if (!cancelled) { setRows(r); setMore(r.length === PAGE) } })
      .catch(() => { if (!cancelled) setError("Could not load the history. Is the backend running?") })
    return () => { cancelled = true }
  }, [fetchPage])

  async function loadMore() {
    setLoadingMore(true)
    try { const r = await fetchPage(rows.length); setRows(x => [...x, ...r]); setMore(r.length === PAGE) } catch { setError("Could not load more.") }
    setLoadingMore(false)
  }

  // group by calendar day, keeping the newest-first order
  const groups = []
  for (const n of rows || []) {
    const label = dayLabel(n.notified_at)
    if (groups.at(-1)?.label === label) groups.at(-1).items.push(n)
    else groups.push({ label, items: [n] })
  }

  return (
    <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 14, maxWidth: 900 }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>Notification history</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
          Every time ChainGuard decided you should be told about an alert: the first time, and again only if it got worse. Repeats of the same facts are not logged.
        </div>
      </div>

      <div style={{ padding: "10px 14px", borderRadius: 8, fontSize: 13, color: "var(--text-primary)", background: "color-mix(in srgb, var(--accent-yellow) 12%, transparent)", border: "1px solid color-mix(in srgb, var(--accent-yellow) 35%, transparent)" }}>
        <b>Nothing is sent yet.</b> No email or chat channel is connected, so these are decisions on record, not messages that reached anyone.
      </div>

      {error && <div style={{ ...card, padding: 14, color: "var(--accent-orange)", fontSize: 13 }}>{error}</div>}
      {!error && rows === null && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>Loading…</div>}
      {rows && rows.length === 0 && !error && (
        <div style={{ ...card, padding: 18, color: "var(--text-secondary)", fontSize: 14, lineHeight: 1.6 }}>
          No notifications so far. Nothing has crossed the notify threshold with enough confidence, which is normal when things are quiet.
          <br />
          <button onClick={() => onNavigate("riskalerts")} style={{ marginTop: 8, background: "none", border: "none", color: "var(--accent-blue)", fontSize: 13, cursor: "pointer", padding: 0 }}>See the alerts being watched →</button>
          {" "}
          <button onClick={() => onNavigate("settings")} style={{ background: "none", border: "none", color: "var(--accent-blue)", fontSize: 13, cursor: "pointer", padding: 0, marginLeft: 12 }}>How alerts are decided →</button>
        </div>
      )}

      {groups.map(g => (
        <div key={g.label} style={{ display: "grid", gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.6, marginTop: 4 }}>{g.label}</div>
          {g.items.map(n => <Row key={n.id} n={n} onOpen={() => onNavigate("riskalerts")} />)}
        </div>
      ))}

      {more && (
        <button onClick={loadMore} disabled={loadingMore} style={{ alignSelf: "center", ...card, borderRadius: 8, color: "var(--text-primary)", fontSize: 13, padding: "8px 18px", cursor: loadingMore ? "not-allowed" : "pointer" }}>
          {loadingMore ? "Loading…" : "Show older"}
        </button>
      )}
    </div>
  )
}
