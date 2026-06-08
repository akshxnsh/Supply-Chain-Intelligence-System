import { useState, useEffect, useRef } from "react"

const API = "http://localhost:8000"

function logLineColor(line) {
  if (line.includes("✅")) return "#4ade80"
  if (line.includes("🔧")) return "#60a5fa"
  if (line.includes("⚠️") || line.includes("❌")) return "#fb923c"
  if (line.includes("⏳")) return "#facc15"
  if (line.includes("🔄")) return "#f1f5f9"
  return "#525252"
}

function Terminal({ businessId, loading, onSimulate }) {
  const [lines, setLines] = useState([])
  const bottomRef = useRef(null)

  // Stream logs via SSE instead of polling
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

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [lines])

  return (
    <div style={{
      background: "var(--bg-card)", border: "1px solid var(--border)",
      borderRadius: 14, overflow: "hidden", marginBottom: 24,
    }}>
      {/* Traffic light header */}
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

      {/* Terminal body */}
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
        {loading && (
          <span style={{ color: "#4ade80" }}>▊</span>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function StepBadge({ n, done }) {
  return (
    <div style={{
      width: 26, height: 26, borderRadius: "50%", flexShrink: 0,
      background: done ? "#3b82f6" : "var(--border)",
      color: done ? "#fff" : "var(--text-muted)",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 11, fontWeight: 700,
    }}>
      {n}
    </div>
  )
}

function TraceTimeline({ result }) {
  const [expanded, setExpanded] = useState({})

  const toolCalls = result?.raw?.tool_calls || result?.tool_calls || []

  if (!result) {
    return (
      <div style={{
        background: "var(--bg-card)", border: "1px solid var(--border)",
        borderRadius: 14, padding: 40, textAlign: "center",
        color: "var(--text-muted)", fontSize: 14,
      }}>
        No trace yet — run a simulation above.
      </div>
    )
  }

  return (
    <div style={{
      background: "var(--bg-card)", border: "1px solid var(--border)",
      borderRadius: 14, padding: 24,
    }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)" }}>
          Last Run Trace
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
          {toolCalls.length} tool calls completed
        </div>
      </div>

      {toolCalls.length === 0 ? (
        <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
          No tool call data captured. The agent may have returned early.
        </div>
      ) : (
        <div style={{ position: "relative" }}>
          {/* Vertical line */}
          <div style={{
            position: "absolute", left: 12, top: 13,
            width: 2, height: `calc(100% - 26px)`,
            background: "var(--border)",
          }} />

          {toolCalls.map((tc, i) => {
            const isOpen = !!expanded[i]
            return (
              <div key={i} style={{ display: "flex", gap: 16, marginBottom: 12, position: "relative" }}>
                <StepBadge n={i + 1} done />
                <div
                  onClick={() => setExpanded(p => ({ ...p, [i]: !p[i] }))}
                  style={{
                    flex: 1, background: "var(--bg-card-hover)",
                    border: "1px solid var(--border)", borderRadius: 10,
                    padding: "10px 14px", cursor: "pointer",
                    transition: "background 0.15s ease",
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = "#1e2d45"}
                  onMouseLeave={e => e.currentTarget.style.background = "var(--bg-card-hover)"}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{
                      fontFamily: "monospace", fontSize: 13,
                      fontWeight: 700, color: "#60a5fa",
                    }}>
                      {tc.tool}
                    </span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {tc.result_len ? `${tc.result_len} chars` : ""} {isOpen ? "▲" : "▼"}
                    </span>
                  </div>
                  {tc.args && Object.keys(tc.args).length > 0 && (
                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>
                      {Object.entries(tc.args).slice(0, 3).map(([k, v]) =>
                        `${k}: ${String(v).slice(0, 40)}`
                      ).join(" · ")}
                    </div>
                  )}
                  {isOpen && (
                    <pre style={{
                      marginTop: 10, padding: 12,
                      background: "#000", borderRadius: 8,
                      fontSize: 11, color: "#a3e635",
                      overflowX: "auto", whiteSpace: "pre-wrap",
                      border: "1px solid var(--border)",
                    }}>
                      {JSON.stringify(tc.args, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function TraceScreen({ businessId, loading, onSimulate, result, error }) {
  return (
    <div style={{ padding: "40px 32px", maxWidth: 960, margin: "0 auto" }}>

      {error && (
        <div style={{
          background: "#1a0a0a", border: "1px solid var(--accent-red)",
          borderRadius: 10, padding: "12px 16px", marginBottom: 20,
          color: "#fca5a5", fontSize: 13,
        }}>
          ❌ {error}
        </div>
      )}

      <Terminal businessId={businessId} loading={loading} onSimulate={onSimulate} />
      <TraceTimeline result={result} />
    </div>
  )
}
