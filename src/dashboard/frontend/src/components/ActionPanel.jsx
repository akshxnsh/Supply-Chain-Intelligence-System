import { useState } from "react"

export default function ActionPanel({ result, approved, onApprove }) {
  const [tab, setTab] = useState("po")

  const ARIZE_URL = "https://app.phoenix.arize.com/s/singhamiya9"

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid #1e2d45",
      borderRadius: 16, padding: 24
    }}>
      <div style={{
        display: "flex", alignItems: "center",
        justifyContent: "space-between", marginBottom: 20
      }}>
        <div style={{
          fontSize: 12, fontWeight: 700,
          color: "var(--text-secondary)",
          letterSpacing: 1, textTransform: "uppercase"
        }}>
          ⚡ Ready-to-Send Actions
        </div>

        <a href={ARIZE_URL} target="_blank" rel="noreferrer" style={{
          fontSize: 12, color: "#3b82f6",
          textDecoration: "none", display: "flex",
          alignItems: "center", gap: 6,
          background: "#0d1a2e",
          border: "1px solid #1e3a5f",
          borderRadius: 8, padding: "6px 12px"
        }}>
          🔍 View Reasoning Trace
        </a>
      </div>

      {/* Tab switcher */}
      <div style={{
        display: "flex", gap: 8, marginBottom: 16
      }}>
        {["po", "email"].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: tab === t ? "#1e3a5f" : "transparent",
            border: `1px solid ${tab === t ? "#3b82f6" : "#1e2d45"}`,
            color: tab === t ? "#3b82f6" : "var(--text-secondary)",
            borderRadius: 8, padding: "6px 16px",
            fontSize: 13, fontWeight: 600, cursor: "pointer"
          }}>
            {t === "po" ? "📄 Purchase Order" : "✉️ Customer Email"}
          </button>
        ))}
      </div>

      {/* Content */}
      <pre style={{
        background: "#070d1a",
        border: "1px solid #1e2d45",
        borderRadius: 10, padding: 20,
        fontSize: 12, color: "#94a3b8",
        whiteSpace: "pre-wrap", lineHeight: 1.7,
        maxHeight: 280, overflowY: "auto",
        fontFamily: "monospace"
      }}>
        {tab === "po"
          ? result?.purchase_order || "No purchase order generated"
          : result?.customer_email || "No email generated"
        }
      </pre>

      {/* Approve button */}
      <div style={{ marginTop: 20, textAlign: "center" }}>
        {approved ? (
          <div style={{
            background: "#0d1f12",
            border: "1px solid #22c55e40",
            borderRadius: 12, padding: "16px 32px",
            display: "inline-flex", alignItems: "center",
            gap: 10, color: "#22c55e",
            fontSize: 15, fontWeight: 700
          }}>
            ✅ Actions Approved & Sent — 6:47 AM
          </div>
        ) : (
          <button onClick={onApprove} style={{
            background: "linear-gradient(135deg, #22c55e, #16a34a)",
            color: "white", border: "none",
            borderRadius: 12, padding: "14px 48px",
            fontSize: 15, fontWeight: 700,
            cursor: "pointer",
            boxShadow: "0 4px 20px rgba(34,197,94,0.3)"
          }}>
            ✅ Approve All Actions
          </button>
        )}
      </div>
    </div>
  )
}