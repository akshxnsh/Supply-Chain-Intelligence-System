import { useState } from "react"

const NAV = [
  { id: "alerts", label: "Alerts",         icon: "🔔" },
  { id: "trace",  label: "Agent Trace",    icon: "⚡" },
  { id: "health", label: "Supplier Health",icon: "📊" },
]

function ZapIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
      stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  )
}

export default function Sidebar({ active, onNavigate }) {
  const [hovered, setHovered] = useState(null)

  return (
    <>
      <style>{`
        @keyframes pulse-dot {
          0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34,197,94,0.4); }
          50% { opacity: 0.8; box-shadow: 0 0 0 4px rgba(34,197,94,0); }
        }
      `}</style>

      <div style={{
        position: "fixed", top: 0, left: 0, width: "var(--sidebar-width)",
        height: "100vh", background: "#050505",
        borderRight: "1px solid var(--border)",
        display: "flex", flexDirection: "column",
        zIndex: 100,
      }}>

        {/* Logo */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "24px 20px 20px",
          borderBottom: "1px solid var(--border)",
        }}>
          <ZapIcon />
          <span style={{ fontWeight: 700, fontSize: 14, color: "#fff", letterSpacing: 0.3 }}>
            SupplyChain AI
          </span>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "12px 10px" }}>
          {NAV.map(item => {
            const isActive = active === item.id
            const isHovered = hovered === item.id
            return (
              <div
                key={item.id}
                onClick={() => onNavigate(item.id)}
                onMouseEnter={() => setHovered(item.id)}
                onMouseLeave={() => setHovered(null)}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "9px 12px",
                  borderRadius: 8,
                  marginBottom: 2,
                  cursor: "pointer",
                  borderLeft: isActive ? "3px solid #3b82f6" : "3px solid transparent",
                  background: isActive
                    ? "rgba(59,130,246,0.10)"
                    : isHovered ? "rgba(255,255,255,0.04)" : "transparent",
                  color: isActive ? "#fff" : isHovered ? "var(--text-secondary)" : "var(--text-muted)",
                  fontWeight: isActive ? 600 : 400,
                  fontSize: 14,
                  transition: "all 0.15s ease",
                  userSelect: "none",
                }}
              >
                <span style={{ fontSize: 15 }}>{item.icon}</span>
                {item.label}
              </div>
            )
          })}
        </nav>

        {/* Footer */}
        <div style={{ padding: "16px 20px", borderTop: "1px solid var(--border)" }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 10 }}>
            Baltimore Bridge Replay · Mar 26 2024
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{
              width: 7, height: 7, borderRadius: "50%",
              background: "#22c55e",
              animation: "pulse-dot 2s ease-in-out infinite",
            }} />
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Live</span>
          </div>
        </div>

      </div>
    </>
  )
}
