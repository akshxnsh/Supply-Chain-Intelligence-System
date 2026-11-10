import { useState, useRef, useEffect } from "react"
import axios from "axios"
import { API } from "../config"

const SUGGESTIONS = [
  "Which alerts matter most right now?",
  "How many days of stock do I have for each product?",
  "Which inbound shipments could be affected?",
  "How fresh is the data?",
]

const TOOL_LABELS = {
  list_open_alerts: "Listed open alerts",
  get_alert_details: "Opened an alert",
  list_shipments: "Listed inbound shipments",
  get_stock_and_orders: "Checked stock and orders",
  data_freshness: "Checked data freshness",
}

// Why a request failed, in words a business user can act on.
function errorText(e) {
  const status = e.response?.status
  const detail = e.response?.data?.detail
  if (status === 429) return "Too many questions in a short time. Please wait a moment and try again."
  if (status === 422) return "Please ask a question between 3 and 500 characters."
  if (status === 404) return typeof detail === "string" ? detail : "That business was not found."
  if (!e.response) return "Cannot reach the ChainGuard server. Is the backend running?"
  return "Something went wrong. Please try again."
}

// Minimal markdown for the model's answer: **bold**, `code`, and "-"/"*" bullet lines. Built as React nodes (never HTML), so it is safe.
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={i} style={{ fontFamily: "monospace", fontSize: 12, background: "var(--bg-card-hover)", borderRadius: 4, padding: "1px 5px" }}>{part.slice(1, -1)}</code>
    }
    return part
  })
}

function Answer({ text }) {
  return text.split(/\n+/).filter(l => l.trim()).map((line, i) => {
    const bullet = line.match(/^\s*[-*]\s+(.*)$/)
    return bullet
      ? <div key={i} style={{ display: "flex", gap: 8, paddingLeft: 4, marginTop: 4 }}><span>•</span><span>{inline(bullet[1])}</span></div>
      : <div key={i} style={{ marginTop: i ? 8 : 0 }}>{inline(line)}</div>
  })
}

function Badge({ color, children, title }) {
  return (
    <span title={title} style={{
      fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999,
      color, background: `color-mix(in srgb, ${color} 14%, transparent)`,
      border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
    }}>{children}</span>
  )
}

function AssistantMessage({ m }) {
  const [open, setOpen] = useState(false)
  const checked = m.grounded
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 760 }}>
      <div style={{
        background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12,
        padding: "12px 14px", color: "var(--text-primary)", fontSize: 14, lineHeight: 1.6,
      }}>
        <Answer text={m.text} />
      </div>

      {!m.error && (
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
          {checked
            ? <Badge color="var(--accent-green)" title="Every number, date and alert id in this answer was found in the data the lookups returned.">Checked against data</Badge>
            : <Badge color="var(--accent-orange)" title={(m.issues || []).join("; ")}>Part could not be verified</Badge>}
          {m.capped && <Badge color="var(--accent-yellow)" title="The assistant hit its limit on lookups or model calls for one question.">Hit a limit</Badge>}
          {(m.cited || []).map(id => (
            <span key={id} title="Alert id" style={{
              fontFamily: "monospace", fontSize: 11, color: "var(--text-secondary)",
              background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: 6, padding: "2px 6px",
            }}>{id}</span>
          ))}
          {m.toolCalls?.length > 0 && (
            <button onClick={() => setOpen(o => !o)} style={{
              background: "transparent", border: "none", color: "var(--accent-blue)", fontSize: 12, cursor: "pointer", padding: 0,
            }}>
              {open ? "Hide" : "Show"} what it looked up ({m.toolCalls.length})
            </button>
          )}
          <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: "auto" }}>
            {m.seconds}s · {m.model}
          </span>
        </div>
      )}

      {open && (
        <ul style={{ listStyle: "none", margin: 0, padding: "8px 12px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, color: "var(--text-secondary)" }}>
          {m.toolCalls.map((c, i) => (
            <li key={i} style={{ padding: "2px 0" }}>
              {c.ok === false ? "⚠️" : "✓"} {TOOL_LABELS[c.name] || c.name}
              {Object.keys(c.args || {}).length > 0 && (
                <span style={{ color: "var(--text-muted)", fontFamily: "monospace" }}> {JSON.stringify(c.args)}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function AskScreen({ businessId }) {
  const [messages, setMessages] = useState([])   // {role: "user"|"assistant", text, ...}
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages, busy])

  // A different business is a different conversation.
  useEffect(() => { setMessages([]); setSessionId(null) }, [businessId])

  async function send(question) {
    const q = question.trim()
    if (q.length < 3 || busy) return
    setInput("")
    setMessages(ms => [...ms, { role: "user", text: q }])
    setBusy(true)
    try {
      const { data } = await axios.post(`${API}/api/ask`, { question: q, business_id: businessId, session_id: sessionId }, { timeout: 90000 })
      setSessionId(data.session_id)
      setMessages(ms => [...ms, {
        role: "assistant", text: data.answer, grounded: data.grounded, issues: data.issues, capped: data.capped,
        toolCalls: data.tool_calls, cited: data.cited_alert_ids, seconds: data.seconds, model: data.model, error: !!data.error && !data.tool_calls?.length,
      }])
    } catch (e) {
      setMessages(ms => [...ms, { role: "assistant", text: errorText(e), error: true }])
    } finally {
      setBusy(false)
    }
  }

  function newChat() { setMessages([]); setSessionId(null) }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - var(--header-height))", padding: "20px 24px 16px", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>Ask ChainGuard</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
            Read-only. It answers only from your alerts, shipments, stock and data freshness, and cannot change anything.
          </div>
        </div>
        {messages.length > 0 && (
          <button onClick={newChat} style={{
            background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8,
            color: "var(--text-secondary)", padding: "6px 12px", fontSize: 12, cursor: "pointer",
          }}>New chat</button>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 14, paddingRight: 4 }}>
        {messages.length === 0 && (
          <div style={{ margin: "auto", textAlign: "center", maxWidth: 520 }}>
            <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 14 }}>Try one of these, or type your own question.</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
              {SUGGESTIONS.map(s => (
                <button key={s} onClick={() => send(s)} style={{
                  background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 999,
                  color: "var(--text-primary)", padding: "8px 14px", fontSize: 13, cursor: "pointer",
                }}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => m.role === "user" ? (
          <div key={i} style={{
            alignSelf: "flex-end", maxWidth: 560, background: "var(--accent-blue)", color: "#fff",
            borderRadius: 12, padding: "10px 14px", fontSize: 14, lineHeight: 1.5,
          }}>{m.text}</div>
        ) : <AssistantMessage key={i} m={m} />)}

        {busy && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>Looking things up…</div>}
        <div ref={endRef} />
      </div>

      <form onSubmit={e => { e.preventDefault(); send(input) }} style={{ display: "flex", gap: 8 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          maxLength={500}
          placeholder="Ask about alerts, shipments, stock or data freshness…"
          disabled={busy}
          style={{
            flex: 1, background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 10,
            color: "var(--text-primary)", padding: "11px 14px", fontSize: 14, outline: "none",
          }}
        />
        <button type="submit" disabled={busy || input.trim().length < 3} style={{
          background: "var(--accent-blue)", border: "none", borderRadius: 10, color: "#fff", fontWeight: 600,
          padding: "0 20px", fontSize: 14, cursor: busy || input.trim().length < 3 ? "not-allowed" : "pointer",
          opacity: busy || input.trim().length < 3 ? 0.5 : 1,
        }}>Ask</button>
      </form>
    </div>
  )
}
