function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function SeverityPill({ exposure }) {
  let label, color, bg;
  if (exposure > 50000) {
    label = "CRITICAL";
    color = "#ef4444";
    bg = "rgba(239,68,68,0.12)";
  } else if (exposure > 20000) {
    label = "ELEVATED";
    color = "#f97316";
    bg = "rgba(249,115,22,0.12)";
  } else {
    label = "MODERATE";
    color = "#eab308";
    bg = "rgba(234,179,8,0.12)";
  }
  return (
    <span style={{
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: 1,
      textTransform: "uppercase",
      color,
      background: bg,
      border: `1px solid ${color}40`,
      borderRadius: 6,
      padding: "3px 10px",
    }}>
      {label}
    </span>
  );
}

function LoadingSkeleton() {
  const shimmer = {
    background: "linear-gradient(90deg, #1e2d45 25%, #253550 50%, #1e2d45 75%)",
    backgroundSize: "200% 100%",
    animation: "shimmer 1.4s infinite",
    borderRadius: 8,
  };
  return (
    <>
      <style>{`@keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ ...shimmer, height: 18, width: "55%" }} />
        <div style={{ ...shimmer, height: 48, width: "75%" }} />
        <div style={{ ...shimmer, height: 18, width: "45%" }} />
      </div>
    </>
  );
}

export default function ExposureCard({ exposure, supplier, expectedLoss, inventoryValue }) {
  const isLoading = exposure === null || exposure === undefined;

  const coveragePct = inventoryValue && exposure
    ? Math.round((inventoryValue / exposure) * 100)
    : null;

  const coverageColor =
    coveragePct >= 80
      ? "#22c55e"
      : coveragePct >= 40
      ? "#eab308"
      : "#ef4444";

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border)",
      borderRadius: 16,
      padding: 24,
    }}>
      {isLoading ? (
        <LoadingSkeleton />
      ) : (
        <>
          {/* Header row */}
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 20,
          }}>
            <div style={{
              fontSize: 12,
              fontWeight: 700,
              color: "var(--text-secondary)",
              letterSpacing: 1,
              textTransform: "uppercase",
            }}>
              Financial Exposure
            </div>
            <SeverityPill exposure={exposure} />
          </div>

          {/* Large exposure number */}
          <div style={{ marginBottom: 20 }}>
            <div style={{
              fontSize: 42,
              fontWeight: 800,
              color: "var(--text-primary)",
              letterSpacing: -1,
              lineHeight: 1,
              marginBottom: 4,
            }}>
              {formatCurrency(exposure)}
            </div>
            <div style={{
              fontSize: 12,
              color: "var(--text-muted)",
              fontWeight: 500,
              textTransform: "uppercase",
              letterSpacing: 0.5,
            }}>
              at-risk value
            </div>
          </div>

          {/* Top supplier row */}
          {supplier && (
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 16,
              padding: "10px 14px",
              background: "rgba(59,130,246,0.07)",
              border: "1px solid rgba(59,130,246,0.2)",
              borderRadius: 10,
            }}>
              <div style={{
                fontSize: 12,
                color: "var(--text-secondary)",
                fontWeight: 600,
              }}>
                Recommended Supplier
              </div>
              <div style={{
                fontSize: 13,
                fontWeight: 700,
                color: "#3b82f6",
              }}>
                {supplier}
              </div>
            </div>
          )}

          {/* Expected loss row */}
          {expectedLoss > 0 && (
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 16,
              padding: "10px 14px",
              background: "rgba(239,68,68,0.07)",
              border: "1px solid rgba(239,68,68,0.2)",
              borderRadius: 10,
            }}>
              <div style={{
                fontSize: 12,
                color: "var(--text-secondary)",
                fontWeight: 600,
              }}>
                Expected Loss Without Action
              </div>
              <div style={{
                fontSize: 13,
                fontWeight: 700,
                color: "#ef4444",
              }}>
                {formatCurrency(expectedLoss)}
              </div>
            </div>
          )}

          {/* Inventory coverage section */}
          {inventoryValue !== undefined && inventoryValue !== null && coveragePct !== null && (
            <div style={{ marginTop: 4 }}>
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 8,
              }}>
                <div style={{
                  fontSize: 12,
                  color: "var(--text-secondary)",
                  fontWeight: 600,
                }}>
                  Inventory Coverage
                </div>
                <div style={{
                  fontSize: 13,
                  fontWeight: 700,
                  color: coverageColor,
                }}>
                  {Math.min(coveragePct, 100)}%
                </div>
              </div>
              <div style={{
                width: "100%",
                height: 6,
                background: "var(--border)",
                borderRadius: 99,
                overflow: "hidden",
                marginBottom: 6,
              }}>
                <div style={{
                  width: `${Math.min(coveragePct, 100)}%`,
                  height: "100%",
                  background: coverageColor,
                  borderRadius: 99,
                  transition: "width 0.4s ease",
                }} />
              </div>
              <div style={{
                fontSize: 11,
                color: "var(--text-muted)",
              }}>
                of at-risk exposure covered by existing stock
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}