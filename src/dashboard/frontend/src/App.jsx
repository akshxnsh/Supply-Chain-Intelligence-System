import { useState, useEffect } from "react"
import axios from "axios"
import Sidebar from "./components/Sidebar"
import AlertsScreen from "./screens/AlertsScreen"
import TraceScreen from "./screens/TraceScreen"
import DashboardScreen from "./screens/DashboardScreen"
import RiskDetailsScreen from "./screens/RiskDetailsScreen"
import FreshnessScreen from "./screens/FreshnessScreen"

import { API } from "../config";
const DEFAULT_BIZ = "demo-business-001"

const SCREEN_TITLES = {
  dashboard: "Dashboard",
  risks:     "Active Risks",
  freshness: "Freshness Monitor",
  alerts:    "Active Alerts",
  console:   "Agent Console",
}

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/>
      <line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/>
      <line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  )
}

export default function App() {
  const [screen, setScreen]         = useState("dashboard")
  const [businesses, setBusinesses] = useState([])
  const [businessId, setBusinessId] = useState(DEFAULT_BIZ)
  const [loading, setLoading]       = useState(false)
  const [result, setResult]         = useState(null)
  const [error, setError]           = useState(null)
  const [collapsed, setCollapsed]   = useState(false)
  const [isDark, setIsDark]         = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    document.documentElement.classList.toggle("light", !isDark)
  }, [isDark])

  useEffect(() => {
    axios.get(`${API}/api/businesses`)
      .then(res => setBusinesses(res.data.businesses || []))
      .catch(() => {
        setBusinesses([{ id: DEFAULT_BIZ, name: "Mid-Atlantic Auto Parts Distribution LLC", industry: "Automotive Parts Distribution" }])
      })
  }, [])

  async function simulate() {
    if (loading) return
    setLoading(true)
    setResult(null)
    setError(null)
    setScreen("console")
    try {
      const res = await axios.post(`${API}/api/simulate?business_id=${businessId}`)
      if (res.data.success === false) setError(res.data.error || "Agent failed")
      else {
        setResult(res.data)
        setRefreshKey(k => k + 1)
      }
    } catch (e) {
      setError(e.response?.data?.error || e.message || "Backend not running")
    } finally {
      setLoading(false)
    }
  }

  function handleSelectBusiness(id) {
    setBusinessId(id)
    setResult(null)
    setError(null)
  }

  const businessName = businesses.find(b => b.id === businessId)?.name || businessId
  const sidebarWidth = collapsed ? "var(--sidebar-width-collapsed)" : "var(--sidebar-width)"

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--bg-body)" }}>
      <Sidebar
        active={screen}
        onNavigate={setScreen}
        collapsed={collapsed}
        onToggle={() => setCollapsed(c => !c)}
      />

      <div style={{
        marginLeft: sidebarWidth,
        flex: 1,
        display: "flex",
        flexDirection: "column",
        transition: "margin-left 0.25s ease",
      }}>

        <header style={{
          borderBottom: "1px solid var(--border)",
          padding: "0 24px",
          height: "var(--header-height)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "var(--bg-header)",
          flexShrink: 0,
        }}>
          <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: 15 }}>
            {SCREEN_TITLES[screen]}
          </span>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <select
              value={businessId}
              onChange={e => handleSelectBusiness(e.target.value)}
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                color: "var(--text-primary)",
                padding: "6px 12px",
                fontSize: 13,
                cursor: "pointer",
                outline: "none",
              }}
            >
              {businesses.map(b => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>

            <button
              onClick={() => setIsDark(d => !d)}
              title={isDark ? "Switch to light mode" : "Switch to dark mode"}
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                color: "var(--text-secondary)",
                padding: "6px 10px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                lineHeight: 1,
              }}
            >
              {isDark ? <SunIcon /> : <MoonIcon />}
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{
                width: 8, height: 8, borderRadius: "50%",
                background: "var(--accent-green)",
                boxShadow: "0 0 6px var(--accent-green)",
              }} />
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Online</span>
            </div>
          </div>
        </header>

        <main style={{ flex: 1, overflowY: "auto" }}>
          {screen === "dashboard" && (
            <DashboardScreen
              businessId={businessId}
              businessName={businessName}
              onNavigate={setScreen}
              refreshKey={refreshKey}
            />
          )}
          {screen === "risks" && (
            <RiskDetailsScreen
              businessId={businessId}
              onSimulate={() => { setScreen("console"); simulate() }}
              refreshKey={refreshKey}
            />
          )}
          {screen === "freshness" && <FreshnessScreen />}
          {screen === "alerts"    && <AlertsScreen businessId={businessId} />}
          {screen === "console"   && (
            <TraceScreen
              businessId={businessId}
              loading={loading}
              onSimulate={simulate}
              result={result}
              error={error}
            />
          )}
        </main>

      </div>
    </div>
  )
}
