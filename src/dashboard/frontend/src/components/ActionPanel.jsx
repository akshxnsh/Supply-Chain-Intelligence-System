import { useState } from "react"
import { API } from "../config";
export default function ActionPanel({ result, approved, onApprove, ownerEmail, businessId }) {
  const [copiedPO, setCopiedPO] = useState(false)
  const [copiedEmail, setCopiedEmail] = useState(false)
  const [sending, setSending] = useState(false)
  const [sentAt, setSentAt] = useState(null)
  const [approvalError, setApprovalError] = useState(null)

  if (!result) return null

  const poText = result?.raw?.purchase_order || result?.purchase_order
  const emailText = ownerEmail || result?.raw?.owner_email || result?.customer_email
  const topSupplier = result?.raw?.top_supplier || result?.top_supplier

  const copyToClipboard = (text, setCopied) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleApprove = async () => {
    setSending(true)
    setApprovalError(null)
    try {
      const res = await fetch(`${API}/api/approve-action?business_id=${businessId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          supplier_name: topSupplier,
          purchase_order: poText,
          owner_email: emailText,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || "Approval failed")
      onApprove()
      setSentAt(data?.approved_at || "now")
    } catch (err) {
      setApprovalError(err.message || "An error occurred")
    } finally {
      setSending(false)
    }
  }

  const preStyle = {
    background: "#0a0f1e",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 16,
    fontSize: 12,
    color: "var(--text-secondary)",
    whiteSpace: "pre-wrap",
    lineHeight: 1.7,
    maxHeight: 200,
    overflowY: "auto",
    fontFamily: "monospace",
    margin: 0,
  }

  const blockStyle = {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 12,
    padding: 16,
    flex: 1,
    minWidth: 0,
  }

  const copyBtnStyle = (copied) => ({
    background: copied ? "#166534" : "#1e2d45",
    border: `1px solid ${copied ? "#22c55e40" : "var(--border)"}`,
    color: copied ? "#22c55e" : "var(--text-secondary)",
    borderRadius: 6,
    padding: "4px 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
  })

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border)",
      borderRadius: 16,
      padding: 24,
    }}>
      <div style={{
        fontSize: 12,
        fontWeight: 700,
        color: "var(--text-secondary)",
        letterSpacing: 1,
        textTransform: "uppercase",
        marginBottom: 20,
      }}>
        Ready-to-Send Actions
      </div>

      {/* Two blocks side by side */}
      <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
        {/* Purchase Order block */}
        <div style={blockStyle}>
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 10,
          }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
              Purchase Order Draft
            </span>
            <button
              onClick={() => copyToClipboard(poText || "", setCopiedPO)}
              style={copyBtnStyle(copiedPO)}
            >
              {copiedPO ? "Copied!" : "Copy"}
            </button>
          </div>
          <pre style={preStyle}>
            {poText || "No purchase order generated"}
          </pre>
        </div>

        {/* Email Draft block */}
        <div style={blockStyle}>
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 10,
          }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
              Owner Email Draft
            </span>
            <button
              onClick={() => copyToClipboard(emailText || "", setCopiedEmail)}
              style={copyBtnStyle(copiedEmail)}
            >
              {copiedEmail ? "Copied!" : "Copy"}
            </button>
          </div>
          <pre style={preStyle}>
            {emailText || "No email generated"}
          </pre>
        </div>
      </div>

      {/* Approval action row */}
      <div style={{ textAlign: "center" }}>
        <button
          onClick={handleApprove}
          disabled={approved || sending}
          style={{
            background: approved ? "#1e2d45" : "#16a34a",
            color: approved ? "var(--text-muted)" : "white",
            border: "none",
            borderRadius: 12,
            padding: "14px 48px",
            fontSize: 15,
            fontWeight: 700,
            cursor: approved || sending ? "not-allowed" : "pointer",
            boxShadow: approved ? "none" : "0 4px 20px rgba(34,197,94,0.3)",
            opacity: sending ? 0.7 : 1,
            transition: "background 0.2s, opacity 0.2s",
          }}
        >
          {sending ? "Sending..." : approved ? "Approved" : "Approve & Execute Actions"}
        </button>

        {approved && sentAt && (
          <div style={{
            background: "#0d1f12",
            border: "1px solid #22c55e40",
            borderRadius: 12,
            padding: "14px 28px",
            display: "inline-flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 4,
            marginTop: 16,
          }}>
            <span style={{ color: "#22c55e", fontSize: 15, fontWeight: 700 }}>
              Actions approved and sent
            </span>
            <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
              {sentAt}
            </span>
          </div>
        )}

        {approvalError && (
          <div style={{
            color: "var(--accent-red)",
            fontSize: 13,
            marginTop: 12,
          }}>
            {approvalError}
          </div>
        )}
      </div>

      <a
        href="https://app.phoenix.arize.com/s/singhamiya9"
        target="_blank"
        rel="noreferrer"
        style={{
          color: "var(--text-muted)",
          fontSize: 12,
          textDecoration: "none",
          display: "block",
          textAlign: "right",
          marginTop: 16,
        }}
      >
        View Agent Trace in Arize Phoenix →
      </a>
    </div>
  )
}
