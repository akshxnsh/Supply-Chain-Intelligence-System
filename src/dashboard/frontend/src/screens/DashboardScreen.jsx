import { useState, useEffect } from "react"

import { API } from "../config"

// Home screen. Every number comes from the real pipeline: open risk alerts (/api/risk/alerts),
// the last pipeline run (/api/pipeline/status) and data freshness (/api/freshness).

function usd(n) {
  if (!n) return "$0"
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  return "$" + Math.round(n).toLocaleString("en-US")
}

function ago(iso) {
  if (!iso) return null
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 90) return "just now"
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

function freshnessBadgeColor(pct) {
  if (pct >= 90) return { bg: "rgba(34,197,94,0.12)", color: "#22c55e", border: "rgba(34,197,94,0.3)" }
  if (pct >= 70) return { bg: "rgba(249,115,22,0.12)", color: "#f97316", border: "rgba(249,115,22,0.3)" }
  return { bg: "rgba(239,68,68,0.12)", color: "#ef4444", border: "rgba(239,68,68,0.3)" }
}

const BAND_COLOR = { high: "#22c55e", medium: "#eab308", low: "#f97316" }
const LEVEL_COLOR = { notify: "#ef4444", watch: "#eab308", log: "#94a3b8" }

const card = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12 }
const linkBtn = { background: "none", border: "none", color: "#60a5fa", fontSize: 13, cursor: "pointer", padding: 0 }
const label = { fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }

function get(path) {
  return fetch(`${API}${path}`).then(r => (r.ok ? r.json() : null)).catch(() => null)
}

export default function DashboardScreen({ businessId, businessName, onNavigate, refreshKey }) {
  const [alerts, setAlerts] = useState([])
  const [pipeline, setPipeline] = useState(null)
  const [freshness, setFreshness] = useState(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    // each part appears as soon as its own request is back (the database is a few hundred ms away per call)
    get(`/api/risk/alerts?business_id=${businessId}&limit=100`).then(a => {
      if (cancelled) return
      setFailed(!a || !!a.error)
      setAlerts(a?.alerts || [])
      setLoading(false)
    })
    get("/api/pipeline/status?limit=1").then(p => { if (!cancelled) setPipeline(p) })
    get("/api/freshness").then(f => { if (!cancelled) setFreshness(f) })
    return () => { cancelled = true }
  }, [businessId, refreshKey])

  const notify = alerts.filter(a => a.level === "notify")
  const watch = alerts.filter(a => a.level === "watch")
  const totalLoss = alerts.reduce((s, a) => s + (a.expected_loss_usd || 0), 0)
  const priced = alerts.filter(a => (a.expected_loss_usd || 0) > 0)
  const stockouts = alerts.filter(a => a.stockout_risk).length
  const top = alerts[0]   // the API sorts Notify first, then by expected loss
  const lastRun = pipeline?.recent_runs?.[0]
  const freshPct = freshness?.freshness_pct ?? null
  const freshRows = [...(freshness?.tables || [])].sort((a, b) => (b.is_stale - a.is_stale) || ((b.age_minutes || 0) - (a.age_minutes || 0))).slice(0, 4)

  const stat = (title, value, sub, color, glow) => (
    <div style={{ ...card, borderLeft: `3px solid ${color}`, borderRadius: 14, padding: "20px 24px", boxShadow: glow ? `0 0 12px ${color}33` : "none" }}>
      <div style={{ ...label, color }}>{title}</div>
      <div style={{ fontSize: 36, fontWeight: 800, color: value && value !== "0" && value !== "$0" ? color : "var(--text-primary)" }}>
        {loading ? "—" : value}
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{sub}</div>
    </div>
  )

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 32px" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 28, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Supply Chain Intelligence</h1>
          <div style={{ display: "flex", gap: 16, marginTop: 6, flexWrap: "wrap", fontSize: 13, color: "var(--text-secondary)" }}>
            {lastRun && (
              <span>
                Last analysis: <strong>{ago(lastRun.finished_at || lastRun.started_at)}</strong>
                {lastRun.status !== "ok" && <span style={{ color: "#ef4444" }}> ({lastRun.status})</span>}
              </span>
            )}
            {pipeline?.running && <span style={{ color: "#60a5fa" }}>● analysis running now</span>}
            {businessName && <span>{businessName}</span>}
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, alignItems: "stretch" }}>
          <button onClick={() => onNavigate("ask")} style={{
            background: "rgba(59,130,246,0.1)", border: "1px solid rgba(59,130,246,0.35)", borderRadius: 10,
            color: "#60a5fa", fontSize: 13, fontWeight: 600, padding: "0 16px", cursor: "pointer",
          }}>Ask ChainGuard →</button>
          {freshPct !== null && (() => {
            const fc = freshnessBadgeColor(freshPct)
            return (
              <div style={{ background: fc.bg, border: `1px solid ${fc.border}`, borderRadius: 10, padding: "10px 18px", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>Data Freshness</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: fc.color }}>{freshPct}%</div>
              </div>
            )
          })()}
        </div>
      </div>

      {failed && !loading && (
        <div style={{ ...card, padding: "14px 18px", marginBottom: 20, color: "#f97316", fontSize: 13 }}>
          Could not load alerts. Is the backend running?
        </div>
      )}

      {/* Status cards */}
      {!loading && !failed && alerts.length === 0 ? (
        <div style={{ background: "rgba(34,197,94,0.06)", border: "1px solid rgba(34,197,94,0.3)", borderRadius: 14, padding: "28px 32px", marginBottom: 28, display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#22c55e", flexShrink: 0, boxShadow: "0 0 8px rgba(34,197,94,0.6)" }} />
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>No open alerts</div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 2 }}>Nothing in the news or trade notices currently threatens your shipments.</div>
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 28 }}>
          {stat("Notify", String(notify.length), "act now", "#ef4444", notify.length > 0)}
          {stat("Watch", String(watch.length), stockouts ? `${stockouts} with stockout risk` : "keep an eye on", "#eab308", false)}
          {stat("Expected loss", usd(totalLoss), priced.length ? `across ${priced.length} priced alert${priced.length === 1 ? "" : "s"}` : "no priced alerts", "#60a5fa", false)}
        </div>
      )}

      {/* Top priority */}
      <div style={{ background: "rgba(59,130,246,0.06)", border: "1px solid rgba(59,130,246,0.2)", borderRadius: 12, padding: "18px 22px", marginBottom: 28 }}>
        <div style={{ ...label, color: "#60a5fa" }}>Top priority</div>
        {loading ? (
          <div style={{ fontSize: 14, color: "var(--text-muted)" }}>Loading…</div>
        ) : top ? (
          <>
            <div style={{ fontSize: 15, color: "var(--text-primary)", lineHeight: 1.5, fontWeight: 600 }}>{top.title}</div>
            {top.action && <div style={{ fontSize: 14, color: "var(--text-primary)", marginTop: 8, lineHeight: 1.5 }}>➜ {top.action}</div>}
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 8, display: "flex", gap: 16, flexWrap: "wrap" }}>
              <span>Expected loss <b style={{ color: "var(--text-primary)" }}>{usd(top.expected_loss_usd)}</b></span>
              {top.act_by && <span>Act by <b style={{ color: "var(--text-primary)" }}>{top.act_by}</b></span>}
              <span style={{ color: BAND_COLOR[top.confidence_band] }}>{top.confidence_band} confidence</span>
            </div>
          </>
        ) : (
          <div style={{ fontSize: 14, color: "var(--text-muted)", fontStyle: "italic" }}>Nothing needs your attention right now.</div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, alignItems: "start" }}>

        {/* Top alerts */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Top alerts</h2>
            <button onClick={() => onNavigate("riskalerts")} style={linkBtn}>View all →</button>
          </div>
          {loading ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: 16 }}>Loading…</div>
          ) : alerts.length === 0 ? (
            <div style={{ ...card, borderRadius: 10, padding: "24px 20px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>No open alerts.</div>
          ) : (
            alerts.slice(0, 4).map(a => (
              <div key={a.alert_id} onClick={() => onNavigate("riskalerts")} style={{
                ...card, borderRadius: 10, borderLeft: `3px solid ${LEVEL_COLOR[a.level] || "#94a3b8"}`,
                padding: "12px 16px", marginBottom: 8, cursor: "pointer",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: LEVEL_COLOR[a.level], textTransform: "uppercase", letterSpacing: "0.06em" }}>
                    {a.level}{a.stockout_risk ? " · stockout risk" : ""}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>{usd(a.expected_loss_usd)}</span>
                </div>
                <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.4, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                  {a.title}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Data freshness */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Data Freshness</h2>
            <button onClick={() => onNavigate("freshness")} style={linkBtn}>View all →</button>
          </div>
          {freshness === null ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: 16 }}>Loading…</div>
          ) : freshRows.length === 0 ? (
            <div style={{ ...card, borderRadius: 10, padding: "24px 20px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>No freshness data available.</div>
          ) : (
            freshRows.map(row => (
              <div key={row.table_name} style={{
                ...card, borderRadius: 10, borderLeft: `3px solid ${row.is_stale ? "#f97316" : "#22c55e"}`,
                padding: "12px 16px", marginBottom: 8, display: "flex", alignItems: "center", justifyContent: "space-between",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 14 }}>{row.is_stale ? "⚠️" : "✅"}</span>
                  <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", fontFamily: "monospace" }}>{row.table_name}</span>
                </div>
                <div style={{ fontSize: 12, color: row.is_stale ? "#f97316" : "var(--text-muted)", fontWeight: row.is_stale ? 600 : 400 }}>
                  {Math.round(row.age_minutes || 0)} min ago
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
