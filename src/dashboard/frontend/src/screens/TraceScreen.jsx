import { useState, useEffect, useRef } from "react"

import { API } from "../config";
// ── Friendly labels for each tool ──────────────────────────────────────────────
const TOOL_LABELS = {
  // freshness
  check_bigquery_table_freshness: "🕒 Checking data freshness",
  identify_stale_tables:          "🧭 Identifying stale tables",
  refresh_connector:              "🔄 Triggering connector refresh",
  get_connector_status:           "📡 Checking connector status",
  wait_for_connector_completion:  "⏳ Waiting for sync",
  sync_postgres_table_to_bigquery:"🔁 Syncing Postgres → BigQuery",
  refresh_stale_table:            "🔄 Refreshing stale data",
  refresh_all_stale_tables:       "🔄 Refreshing all stale data",
  // disruption / impact
  get_recent_disruptions:         "🔍 Checking disruptions",
  detect_disruptions:             "🔍 Detecting disruptions",
  detect_black_swan:              "⚠️ Black Swan analysis",
  get_weather_alerts:             "🌧️ Checking weather alerts",
  get_port_activity:              "⚓ Checking port activity",
  get_port_status:                "⚓ Checking port status",
  get_tariff_updates:             "📜 Checking tariff updates",
  calculate_impact:               "💥 Calculating impact",
  calculate_exposure:             "💰 Calculating exposure",
  // inventory / orders / suppliers
  get_inventory:                  "📦 Checking inventory",
  get_pending_orders:             "📋 Reviewing pending orders",
  get_shipment_timetable:         "🚚 Checking inbound shipments",
  get_business_suppliers:         "🏢 Loading suppliers",
  get_supplier_reviews:           "⭐ Reading supplier reviews",
  score_suppliers:                "📊 Scoring suppliers",
  search_alternative_suppliers:   "🏭 Finding alternatives",
  // calibration / procurement / output
  query_calibration_baseline:     "🎯 Loading calibration baseline",
  query_recent_cycle_performance: "📈 Reviewing recent performance",
  get_severity_calibration_drift: "🎚️ Checking calibration drift",
  generate_purchase_order:        "🧾 Drafting purchase order",
  generate_owner_email:           "✉️ Drafting owner email",
  save_alert_record:              "💾 Saving alert",
}

function toolLabel(tool) {
  return TOOL_LABELS[tool] || tool
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function formatExposure(usd) {
  if (!usd) return "$0"
  if (usd >= 1_000_000) return `$${(usd / 1_000_000).toFixed(1)}M`
  if (usd >= 1_000) return `$${Math.round(usd / 1_000)}K`
  return `$${Number(usd).toLocaleString("en-US")}`
}

function formatDuration(ms) {
  if (ms == null) return null
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

function confidenceColor(pct) {
  if (pct >= 80) return "#22c55e"
  if (pct >= 60) return "#f97316"
  return "#ef4444"
}

function severityColor(score100) {
  if (score100 >= 80) return "#ef4444"
  if (score100 >= 50) return "#f97316"
  return "#eab308"
}

// Pull a short human preview from a (possibly JSON-string) tool response
function responsePreview(response) {
  if (response == null) return null
  let text = typeof response === "string" ? response : JSON.stringify(response)
  try {
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === "object") {
      if (Array.isArray(parsed)) {
        text = `${parsed.length} item${parsed.length !== 1 ? "s" : ""}`
      } else {
        // surface a few telling keys if present, else compact JSON
        const keys = Object.keys(parsed)
        const telling = ["headline", "summary", "is_stale", "status", "sync_state",
                         "stale_count", "severity_score", "count", "message", "name"]
          .filter(k => k in parsed)
        if (telling.length) {
          text = telling.map(k => `${k}: ${String(parsed[k])}`).join(" · ")
        } else {
          text = keys.slice(0, 4).map(k => `${k}: ${String(parsed[k]).slice(0, 30)}`).join(" · ")
        }
      }
    }
  } catch {
    // not JSON — keep raw text
  }
  return text.length > 160 ? text.slice(0, 160) + "…" : text
}

// Agent display metadata
function agentMeta(author) {
  if (!author || author === "SupplyChainIntelligenceAgent") {
    return { icon: "🤖", label: "RootAgent", color: "#60a5fa", bg: "rgba(96,165,250,0.08)", border: "rgba(96,165,250,0.3)" }
  }
  if (author === "FreshnessAgent") {
    return { icon: "🟠", label: "FreshnessAgent", color: "#f97316", bg: "rgba(249,115,22,0.08)", border: "rgba(249,115,22,0.3)" }
  }
  return { icon: "🔹", label: author, color: "var(--text-secondary)", bg: "var(--bg-card-hover)", border: "var(--border)" }
}

// Group consecutive tool calls into agent blocks (re-entry = new block)
function groupByAgent(toolCalls) {
  const blocks = []
  let current = null
  let stepNo = 0
  for (const tc of toolCalls) {
    stepNo += 1
    const author = tc.author || "SupplyChainIntelligenceAgent"
    if (!current || current.author !== author) {
      current = { author, steps: [] }
      blocks.push(current)
    }
    current.steps.push({ ...tc, stepNo })
  }
  return blocks
}

const logLineColor = (line) => {
  if (line.includes("✅")) return "#4ade80"
  if (line.includes("🔧")) return "#60a5fa"
  if (line.includes("⚠️") || line.includes("❌")) return "#fb923c"
  if (line.includes("⏳")) return "#facc15"
  if (line.includes("🔄")) return "#f1f5f9"
  return "#525252"
}

// ── Live Log Terminal (SSE) — unchanged behavior ───────────────────────────────
function Terminal({ businessId, loading, onSimulate }) {
  const [lines, setLines] = useState([])
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!loading) return
    setLines([])
    const es = new EventSource(`${API}/api/live-log/stream?business_id=${encodeURIComponent(businessId)}`)
    es.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.log) setLines(prev => [...prev, data.log])
      if (data.done) es.close()
    }
    es.onerror = () => es.close()
    return () => es.close()
  }, [loading])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [lines])

  return (
    <div style={{
      background: "var(--bg-card)", border: "1px solid var(--border)",
      borderRadius: 14, overflow: "hidden",
    }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "12px 16px", background: "#0d0d0d",
        borderBottom: "1px solid var(--border)",
      }}>
        <div style={{ display: "flex", gap: 6 }}>
          <div style={{ width: 12, height: 12, borderRadius: "50%", background: "#ff5f57" }} />
          <div style={{ width: 12, height: 12, borderRadius: "50%", background: "#ffbd2e" }} />
          <div style={{ width: 12, height: 12, borderRadius: "50%", background: "#28c840" }} />
        </div>
        <span style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>
          agent-simulation
        </span>
        <button
          onClick={onSimulate}
          disabled={loading}
          style={{
            background: loading ? "var(--border)" : "#3b82f6",
            color: loading ? "var(--text-muted)" : "#fff",
            border: "none", borderRadius: 6,
            padding: "6px 14px", fontSize: 12, fontWeight: 600,
            cursor: loading ? "not-allowed" : "pointer",
            transition: "all 0.15s ease",
          }}
        >
          {loading ? "Running…" : "Run Simulation"}
        </button>
      </div>

      <div style={{
        background: "#000", fontFamily: "monospace", fontSize: 13,
        padding: "16px", minHeight: 320, maxHeight: 420,
        overflowY: "auto", lineHeight: 1.6,
      }}>
        {lines.length === 0 && !loading && (
          <span style={{ color: "#22c55e80" }}>
            $ Ready. Click &apos;Run Simulation&apos; to start the agent cycle.
          </span>
        )}
        {lines.map((line, i) => (
          <div key={i} style={{ color: logLineColor(line) }}>{line}</div>
        ))}
        {loading && <span style={{ color: "#4ade80" }}>▊</span>}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Run Summary card ───────────────────────────────────────────────────────────
function RunSummary({ raw, toolCount }) {
  if (!raw || Object.keys(raw).length === 0) {
    return (
      <div style={{
        background: "var(--bg-card)", border: "1px solid var(--border)",
        borderRadius: 14, padding: "24px 28px", marginBottom: 20,
        color: "var(--text-muted)", fontSize: 14, textAlign: "center",
      }}>
        Run a simulation to see the agent&apos;s run summary.
      </div>
    )
  }

  const blackSwan = raw.black_swan_detected
  const alertFired = raw.alert_fired
  const status = blackSwan
    ? { text: "🦢 Black Swan — Human Review", color: "#ef4444" }
    : alertFired
      ? { text: "🚨 Alert Generated", color: "#ef4444" }
      : { text: "✅ No Alert", color: "#22c55e" }

  const sev100 = Math.round(Number(raw.severity_score || 0) * 10)
  const confPct = Math.round(Number(raw.calibration_confidence || 0) * 100)
  const suppliers = (raw.affected_suppliers || []).length

  const Metric = ({ label, value, color }) => (
    <div style={{ minWidth: 90 }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color: color || "var(--text-primary)" }}>{value}</div>
    </div>
  )

  return (
    <div style={{
      background: "var(--bg-card)", border: "1px solid var(--border)",
      borderLeft: `4px solid ${status.color}`,
      borderRadius: 14, padding: "20px 28px", marginBottom: 20,
      display: "flex", alignItems: "center", gap: 32, flexWrap: "wrap",
    }}>
      <div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>
          Status
        </div>
        <div style={{ fontSize: 16, fontWeight: 700, color: status.color }}>{status.text}</div>
      </div>
      <div style={{ width: 1, height: 40, background: "var(--border)" }} />
      <Metric label="Severity" value={`${sev100}/100`} color={severityColor(sev100)} />
      <Metric label="Confidence" value={`${confPct}%`} color={confidenceColor(confPct)} />
      <Metric label="Exposure" value={formatExposure(raw.exposure_usd)} color="#f97316" />
      <Metric label="Suppliers" value={suppliers} />
      <Metric label="Tools Used" value={toolCount} />
    </div>
  )
}

// ── Tabs ───────────────────────────────────────────────────────────────────────
const TABS = ["Overview", "Timeline", "Tools", "Live Log", "Raw JSON"]

function TabBar({ active, onChange }) {
  return (
    <div style={{ display: "flex", gap: 6, marginBottom: 20, flexWrap: "wrap" }}>
      {TABS.map(t => (
        <button
          key={t}
          onClick={() => onChange(t)}
          style={{
            background: active === t ? "rgba(59,130,246,0.15)" : "transparent",
            border: `1px solid ${active === t ? "rgba(59,130,246,0.5)" : "var(--border)"}`,
            borderRadius: 20,
            color: active === t ? "#60a5fa" : "var(--text-secondary)",
            fontSize: 13, fontWeight: active === t ? 600 : 400,
            padding: "5px 16px", cursor: "pointer",
          }}
        >
          {t}
        </button>
      ))}
    </div>
  )
}

function EmptyTab({ children }) {
  return (
    <div style={{
      background: "var(--bg-card)", border: "1px solid var(--border)",
      borderRadius: 14, padding: 40, textAlign: "center",
      color: "var(--text-muted)", fontSize: 14,
    }}>
      {children}
    </div>
  )
}

// ── Overview tab ───────────────────────────────────────────────────────────────
function OverviewTab({ raw }) {
  if (!raw || !Object.keys(raw).length) return <EmptyTab>No analysis yet — run a simulation.</EmptyTab>

  const disruption = raw.disruption || {}
  const headline = disruption.headline || disruption.summary || ""
  const signals = raw.signals_detected || []
  const topAlt = (raw.suggested_alternatives || [])[0]

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: "18px 22px" }}>
        <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
          Disruption
        </div>
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", marginBottom: 8, lineHeight: 1.5 }}>
          {headline || "No disruption headline"}
        </div>
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 13, color: "var(--text-secondary)" }}>
          {(disruption.type || disruption.event_type) && (
            <span><span style={{ color: "var(--text-muted)" }}>Type: </span>{disruption.type || disruption.event_type}</span>
          )}
          {disruption.region && (
            <span><span style={{ color: "var(--text-muted)" }}>Region: </span>{disruption.region}</span>
          )}
        </div>
      </div>

      {signals.length > 0 && (
        <div style={{ background: "rgba(59,130,246,0.05)", border: "1px solid rgba(59,130,246,0.2)", borderRadius: 12, padding: "18px 22px" }}>
          <div style={{ fontSize: 11, color: "#60a5fa", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>
            Why Flagged
          </div>
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {signals.map((s, i) => (
              <li key={i} style={{ fontSize: 14, color: "var(--text-primary)", lineHeight: 1.6, paddingLeft: 18, position: "relative", marginBottom: 4 }}>
                <span style={{ position: "absolute", left: 0, color: "#60a5fa" }}>•</span>{s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {topAlt && (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderLeft: "3px solid #22c55e", borderRadius: 12, padding: "16px 22px" }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
            Top Recommended Alternative
          </div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
            {topAlt.name} <span style={{ fontSize: 13, fontWeight: 400, color: "var(--text-muted)" }}>{topAlt.country}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Timeline tab (agent blocks) ────────────────────────────────────────────────
function TimelineTab({ toolCalls }) {
  if (!toolCalls.length) return <EmptyTab>No tool calls captured — run a simulation.</EmptyTab>

  const blocks = groupByAgent(toolCalls)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {blocks.map((block, bi) => {
        const meta = agentMeta(block.author)
        return (
          <div key={bi}>
            <div style={{
              background: meta.bg, border: `1px solid ${meta.border}`,
              borderRadius: 12, overflow: "hidden",
            }}>
              {/* Agent header */}
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "10px 16px", borderBottom: `1px solid ${meta.border}`,
              }}>
                <span style={{ fontSize: 15 }}>{meta.icon}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: meta.color }}>{meta.label}</span>
                <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: "auto" }}>
                  {block.steps.length} step{block.steps.length !== 1 ? "s" : ""}
                </span>
              </div>
              {/* Steps */}
              <div style={{ padding: "8px 12px" }}>
                {block.steps.map((step, si) => {
                  const preview = responsePreview(step.response)
                  const dur = formatDuration(step.duration_ms)
                  return (
                    <div key={si} style={{
                      display: "flex", gap: 12, padding: "8px 8px",
                      borderBottom: si < block.steps.length - 1 ? "1px solid var(--border)" : "none",
                    }}>
                      <div style={{
                        width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
                        background: meta.color, color: "#fff",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 10, fontWeight: 700,
                      }}>
                        {step.stepNo}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                            {toolLabel(step.tool)}
                          </span>
                          <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--text-muted)" }}>
                            {step.tool}
                          </span>
                          {dur && (
                            <span style={{
                              fontSize: 11, color: "var(--text-secondary)", fontWeight: 600,
                              background: "var(--bg-card)", borderRadius: 6, padding: "1px 7px",
                            }}>
                              {dur}
                            </span>
                          )}
                        </div>
                        {preview && (
                          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 3, lineHeight: 1.5, wordBreak: "break-word" }}>
                            → {preview}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
            {bi < blocks.length - 1 && (
              <div style={{ textAlign: "center", color: "var(--text-muted)", fontSize: 18, padding: "4px 0" }}>↓</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Tools tab (raw expandable) ─────────────────────────────────────────────────
function ToolsTab({ toolCalls }) {
  const [expanded, setExpanded] = useState({})
  if (!toolCalls.length) return <EmptyTab>No tool calls captured — run a simulation.</EmptyTab>

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {toolCalls.map((tc, i) => {
        const isOpen = !!expanded[i]
        return (
          <div key={i} style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 10 }}>
            <div
              onClick={() => setExpanded(p => ({ ...p, [i]: !p[i] }))}
              style={{ padding: "10px 14px", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700, color: "#60a5fa" }}>{tc.tool}</span>
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{agentMeta(tc.author).label}</span>
                {tc.duration_ms != null && (
                  <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{formatDuration(tc.duration_ms)}</span>
                )}
              </div>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{isOpen ? "▲" : "▼"}</span>
            </div>
            {isOpen && (
              <div style={{ padding: "0 14px 14px" }}>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Arguments</div>
                <pre style={{ margin: 0, padding: 10, background: "#000", borderRadius: 8, fontSize: 11, color: "#a3e635", overflowX: "auto", whiteSpace: "pre-wrap", border: "1px solid var(--border)" }}>
                  {JSON.stringify(tc.args || {}, null, 2)}
                </pre>
                {tc.response != null && (
                  <>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", margin: "10px 0 4px" }}>Response</div>
                    <pre style={{ margin: 0, padding: 10, background: "#000", borderRadius: 8, fontSize: 11, color: "#7dd3fc", overflowX: "auto", whiteSpace: "pre-wrap", border: "1px solid var(--border)" }}>
                      {typeof tc.response === "string" ? tc.response : JSON.stringify(tc.response, null, 2)}
                    </pre>
                  </>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Main screen ────────────────────────────────────────────────────────────────
export default function TraceScreen({ businessId, loading, onSimulate, result, error }) {
  const [tab, setTab] = useState("Timeline")
  const raw = result?.raw || result || {}
  const toolCalls = raw.tool_calls || result?.tool_calls || []

  return (
    <div style={{ padding: "40px 32px", maxWidth: 960, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
          Agent Console
        </h1>
        <span style={{
          background: "rgba(139,92,246,0.2)", color: "#8b5cf6",
          border: "1px solid rgba(139,92,246,0.4)", borderRadius: 6,
          padding: "2px 8px", fontSize: 11, fontWeight: 600,
        }}>
          DEV
        </span>
        <button
          onClick={onSimulate}
          disabled={loading}
          style={{
            marginLeft: "auto",
            background: loading ? "var(--border)" : "#3b82f6",
            color: loading ? "var(--text-muted)" : "#fff",
            border: "none", borderRadius: 8,
            padding: "8px 18px", fontSize: 13, fontWeight: 600,
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Running…" : "Run Simulation"}
        </button>
      </div>

      {error && (
        <div style={{
          background: "#1a0a0a", border: "1px solid var(--accent-red)",
          borderRadius: 10, padding: "12px 16px", marginBottom: 20,
          color: "#fca5a5", fontSize: 13,
        }}>
          ❌ {error}
        </div>
      )}

      <RunSummary raw={raw} toolCount={toolCalls.length} />

      <TabBar active={tab} onChange={setTab} />

      {tab === "Overview" && <OverviewTab raw={raw} />}
      {tab === "Timeline" && <TimelineTab toolCalls={toolCalls} />}
      {tab === "Tools"    && <ToolsTab toolCalls={toolCalls} />}
      {tab === "Live Log" && <Terminal businessId={businessId} loading={loading} onSimulate={onSimulate} />}
      {tab === "Raw JSON" && (
        Object.keys(raw).length ? (
          <pre style={{
            background: "#000", border: "1px solid var(--border)", borderRadius: 12,
            padding: 16, fontSize: 11, color: "#a3e635", overflowX: "auto",
            whiteSpace: "pre-wrap", lineHeight: 1.5, maxHeight: 600,
          }}>
            {JSON.stringify(raw, null, 2)}
          </pre>
        ) : <EmptyTab>No run data yet — run a simulation.</EmptyTab>
      )}
    </div>
  )
}
