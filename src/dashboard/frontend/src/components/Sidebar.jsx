const NAV = [
  { id: "overview", label: "Overview",        Icon: IconGrid },
  { id: "alerts",   label: "Alerts",          Icon: IconBell },
  { id: "trace",    label: "Agent Trace",     Icon: IconActivity },
  { id: "health",   label: "Supplier Health", Icon: IconBarChart },
]

function IconGrid({ size = 17, color = "currentColor" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  )
}

function IconBell({ size = 17, color = "currentColor" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  )
}

function IconActivity({ size = 17, color = "currentColor" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  )
}

function IconBarChart({ size = 17, color = "currentColor" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6"  y1="20" x2="6"  y2="14" />
      <line x1="2"  y1="20" x2="22" y2="20" />
    </svg>
  )
}

function ZapIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
      stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  )
}

function ChevronIcon({ collapsed }) {
  return (
    <svg
      width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      style={{ transition: "transform 0.25s ease", transform: collapsed ? "rotate(180deg)" : "rotate(0deg)" }}
    >
      <polyline points="15 18 9 12 15 6" />
    </svg>
  )
}

export default function Sidebar({ active, onNavigate, collapsed, onToggle }) {
  const width = collapsed ? "var(--sidebar-width-collapsed)" : "var(--sidebar-width)"

  return (
    <div style={{
      position: "fixed", top: 0, left: 0,
      width,
      height: "100vh",
      background: "var(--bg-sidebar)",
      borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
      zIndex: 100,
      transition: "width 0.25s ease",
      overflow: "hidden",
    }}>

      {/* Logo row */}
      <div style={{
        height: "var(--header-height)",
        display: "flex",
        alignItems: "center",
        justifyContent: collapsed ? "center" : "space-between",
        padding: collapsed ? "0" : "0 14px 0 16px",
        borderBottom: "1px solid var(--border)",
        flexShrink: 0,
      }}>
        {!collapsed && (
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <ZapIcon />
            <span style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)", letterSpacing: 0.3, whiteSpace: "nowrap" }}>
              SupplyChain AI
            </span>
          </div>
        )}

        <button
          onClick={onToggle}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 6,
            borderRadius: 6,
            flexShrink: 0,
          }}
        >
          {collapsed ? <ZapIcon /> : <ChevronIcon collapsed={false} />}
        </button>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: "12px 8px" }}>
        {NAV.map(({ id, label, Icon }) => {
          const isActive = active === id
          return (
            <div
              key={id}
              onClick={() => onNavigate(id)}
              title={collapsed ? label : undefined}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: collapsed ? "center" : "flex-start",
                gap: 10,
                padding: collapsed ? "9px 0" : "9px 12px",
                borderRadius: 8,
                marginBottom: 2,
                cursor: "pointer",
                borderLeft: isActive && !collapsed ? "3px solid #3b82f6" : "3px solid transparent",
                background: isActive ? "rgba(59,130,246,0.10)" : "transparent",
                color: isActive ? "var(--accent-blue)" : "var(--text-muted)",
                fontWeight: isActive ? 600 : 400,
                fontSize: 13.5,
                transition: "all 0.15s ease",
                userSelect: "none",
                whiteSpace: "nowrap",
                overflow: "hidden",
              }}
              onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; e.currentTarget.style.color = "var(--text-secondary)" } }}
              onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-muted)" } }}
            >
              <span style={{ flexShrink: 0, display: "flex", alignItems: "center" }}>
                <Icon size={17} />
              </span>
              {!collapsed && label}
            </div>
          )
        })}
      </nav>

      {/* Footer */}
      {!collapsed && (
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
      )}

      {collapsed && (
        <div style={{ padding: "16px 0", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "center" }}>
          <div style={{
            width: 7, height: 7, borderRadius: "50%",
            background: "#22c55e",
            animation: "pulse-dot 2s ease-in-out infinite",
          }} />
        </div>
      )}
    </div>
  )
}
