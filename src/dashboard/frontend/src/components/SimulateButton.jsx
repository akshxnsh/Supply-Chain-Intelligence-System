export default function SimulateButton({ loading, onClick }) {
  return (
    <div style={{ textAlign: "center", padding: "16px 0" }}>
      <p style={{
        color: "var(--text-secondary)", fontSize: 14, marginBottom: 16
      }}>
        Simulate a real-world supply chain disruption to see the agent in action
      </p>
      <button
        onClick={onClick}
        disabled={loading}
        style={{
          background: loading
            ? "#1e2d45"
            : "linear-gradient(135deg, #ef4444, #dc2626)",
          color: "white",
          border: "none",
          borderRadius: 12,
          padding: "14px 40px",
          fontSize: 15,
          fontWeight: 700,
          cursor: loading ? "not-allowed" : "pointer",
          display: "inline-flex",
          alignItems: "center",
          gap: 10,
          transition: "all 0.2s",
          boxShadow: loading ? "none" : "0 4px 20px rgba(239,68,68,0.3)"
        }}
      >
        {loading ? (
          <>
            <span style={{
              display: "inline-block",
              width: 16, height: 16,
              border: "2px solid #ffffff40",
              borderTopColor: "white",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite"
            }} />
            Agent Analyzing...
          </>
        ) : (
          <>🌀 Simulate Disruption</>
        )}
      </button>
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}