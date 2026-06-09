import { useState, useEffect } from "react";

function IconBuilding({ size = 20, color = "currentColor" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18" />
      <path d="M9 21V9" />
    </svg>
  )
}

function IconDollar({ size = 20, color = "currentColor" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="1" x2="12" y2="23" />
      <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </svg>
  )
}

function IconGlobe({ size = 20, color = "currentColor" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  )
}

function IconAlertTriangle({ size = 11, color = "#f97316" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

const CARD_ICONS = {
  "Total Suppliers":    <IconBuilding size={20} color="#3b82f6" />,
  "Total Annual Spend": <IconDollar   size={20} color="#22c55e" />,
  "Countries":          <IconGlobe    size={20} color="#a855f7" />,
}

const CATEGORY_COLORS = {
  auto_parts: "#3b82f6",
  fasteners: "#22c55e",
  semiconductors: "#a855f7",
  circuit_boards: "#f97316",
  displays: "#14b8a6",
  roofing_materials: "#6b7280",
};

function categoryColor(cat) {
  return CATEGORY_COLORS[cat] || "#6b7280";
}

function countryFlag(country) {
  const flags = {
    China: "🇨🇳", USA: "🇺🇸", Germany: "🇩🇪", Japan: "🇯🇵",
    India: "🇮🇳", Taiwan: "🇹🇼", Mexico: "🇲🇽", "South Korea": "🇰🇷",
    UK: "🇬🇧", France: "🇫🇷", Canada: "🇨🇦", Brazil: "🇧🇷",
    Vietnam: "🇻🇳", Thailand: "🇹🇭", Malaysia: "🇲🇾",
  };
  return flags[country] || "🌍";
}

function formatSpend(val) {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${Math.round(val / 1_000)}k`;
  return `$${val}`;
}

function healthBadge(supplier) {
  const { annual_spend_usd: spend, other_suppliers_count, avg_delay_days } = supplier;
  const isSingleSource = other_suppliers_count === 0;
  const hasHighDelay   = avg_delay_days != null && avg_delay_days > 7;
  if (isSingleSource || hasHighDelay)
    return { label: "At Risk", color: "#ef4444", bg: "#1f0505" };
  if (spend < 100_000 || (avg_delay_days != null && avg_delay_days > 3))
    return { label: "Monitor", color: "#eab308", bg: "#1c1a05" };
  return { label: "Healthy", color: "#22c55e", bg: "#052e16" };
}

function SkeletonRow() {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 16,
      padding: "16px 20px", borderBottom: "1px solid var(--border)",
    }}>
      {[200, 120, 100, 160].map((w, i) => (
        <div key={i} style={{
          width: w, height: 16, borderRadius: 6,
          background: "linear-gradient(90deg, #1e2d45 25%, #253450 50%, #1e2d45 75%)",
          backgroundSize: "400% 100%",
          animation: "shimmer 1.4s infinite",
          flexShrink: 0,
        }} />
      ))}
    </div>
  );
}

export default function SupplierHealthScreen({ businessId }) {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [hoveredRow, setHoveredRow] = useState(null);

  useEffect(() => {
    if (!businessId) return;
    setLoading(true);
    setError(null);
    fetch(`http://localhost:8000/api/suppliers?business_id=${businessId}`)
      .then((r) => r.json())
      .then((data) => {
        const sorted = [...(data.suppliers || [])].sort(
          (a, b) => b.annual_spend_usd - a.annual_spend_usd
        );
        setSuppliers(sorted);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [businessId]);

  const filtered = suppliers.filter(
    (s) =>
      s.supplier_name.toLowerCase().includes(search.toLowerCase()) ||
      s.country.toLowerCase().includes(search.toLowerCase())
  );

  const totalSpend = suppliers.reduce((a, s) => a + s.annual_spend_usd, 0);
  const uniqueCountries = new Set(suppliers.map((s) => s.country)).size;
  const maxSpend = suppliers[0]?.annual_spend_usd || 1;

  const categoryBreakdown = suppliers.reduce((acc, s) => {
    acc[s.product_category] = (acc[s.product_category] || 0) + s.annual_spend_usd;
    return acc;
  }, {});

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg-primary)",
      padding: "40px 32px",
    }}>
      <style>{`
        @keyframes shimmer {
          0% { background-position: 100% 0; }
          100% { background-position: -100% 0; }
        }
        input::placeholder { color: var(--text-muted); }
        input:focus { outline: none; border-color: var(--accent-blue) !important; }
      `}</style>

      <div style={{ maxWidth: 960, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: 32 }}>
          <h1 style={{
            fontSize: 28, fontWeight: 700, color: "var(--text-primary)",
            margin: 0, letterSpacing: "-0.5px",
          }}>
            Supplier Health
          </h1>
          <p style={{ color: "var(--text-secondary)", margin: "6px 0 0", fontSize: 15 }}>
            Current supplier portfolio and spend analysis
          </p>
        </div>

        {/* Summary Cards */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 28 }}>
          {[
            { label: "Total Suppliers",    value: suppliers.length      },
            { label: "Total Annual Spend", value: formatSpend(totalSpend) },
            { label: "Countries",          value: uniqueCountries         },
          ].map((card, i) => (
            <SummaryCard key={i} {...card} />
          ))}
        </div>

        {/* Search Bar */}
        <div style={{ position: "relative", marginBottom: 20 }}>
          <svg
            style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", opacity: 0.5 }}
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="var(--text-secondary)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search by supplier name or country..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: "100%", boxSizing: "border-box",
              background: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 10, padding: "11px 16px 11px 40px",
              color: "var(--text-primary)", fontSize: 14,
              transition: "all 0.15s ease",
            }}
          />
        </div>

        {/* Table */}
        <div style={{
          background: "var(--bg-card)", border: "1px solid var(--border)",
          borderRadius: 12, overflow: "hidden", marginBottom: 28,
        }}>
          {/* Table Header */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "1.8fr 1.2fr 0.9fr 2fr 140px",
            padding: "12px 20px",
            borderBottom: "1px solid var(--border)",
            background: "#0d1424",
          }}>
            {["Supplier", "Category", "Country", "Annual Spend", "Health"].map((h) => (
              <div key={h} style={{
                fontSize: 11, fontWeight: 600, color: "var(--text-muted)",
                textTransform: "uppercase", letterSpacing: "0.08em",
              }}>{h}</div>
            ))}
          </div>

          {loading && [1, 2, 3, 4].map((i) => <SkeletonRow key={i} />)}

          {!loading && error && (
            <div style={{ padding: 40, textAlign: "center", color: "var(--accent-red)" }}>
              Failed to load suppliers: {error}
            </div>
          )}

          {!loading && !error && filtered.length === 0 && (
            <div style={{
              padding: 60, textAlign: "center",
              color: "var(--text-muted)", fontSize: 15,
            }}>
              {suppliers.length === 0
                ? "No suppliers found for this business."
                : "No results match your search."}
            </div>
          )}

          {!loading && !error && filtered.map((s, i) => {
            const badge = healthBadge(s);
            const barPct = Math.max(4, (s.annual_spend_usd / maxSpend) * 100);
            const isHovered = hoveredRow === i;
            return (
              <div
                key={i}
                onMouseEnter={() => setHoveredRow(i)}
                onMouseLeave={() => setHoveredRow(null)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1.8fr 1.2fr 0.9fr 2fr 140px",
                  alignItems: "center",
                  padding: "14px 20px",
                  borderBottom: i < filtered.length - 1 ? "1px solid var(--border)" : "none",
                  background: isHovered ? "var(--bg-card-hover)" : "transparent",
                  transition: "all 0.15s ease",
                  cursor: "default",
                }}
              >
                {/* Supplier Name */}
                <div>
                  <span style={{ fontSize: 16, marginRight: 6 }}>{countryFlag(s.country)}</span>
                  <span style={{ color: "var(--text-primary)", fontWeight: 500, fontSize: 14 }}>
                    {s.supplier_name}
                  </span>
                </div>

                {/* Category Pill */}
                <div>
                  <span style={{
                    display: "inline-block",
                    background: categoryColor(s.product_category) + "22",
                    color: categoryColor(s.product_category),
                    border: `1px solid ${categoryColor(s.product_category)}44`,
                    borderRadius: 20, padding: "3px 10px",
                    fontSize: 12, fontWeight: 500,
                  }}>
                    {s.product_category.replace(/_/g, " ")}
                  </span>
                </div>

                {/* Country */}
                <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                  {s.country}
                </div>

                {/* Spend Bar */}
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{
                    flex: 1, height: 6, background: "#1e2d45", borderRadius: 3, overflow: "hidden",
                  }}>
                    <div style={{
                      width: `${barPct}%`, height: "100%",
                      background: "linear-gradient(90deg, #3b82f6, #60a5fa)",
                      borderRadius: 3, transition: "width 0.4s ease",
                    }} />
                  </div>
                  <span style={{ color: "var(--text-primary)", fontSize: 13, fontWeight: 500, minWidth: 52, textAlign: "right" }}>
                    {formatSpend(s.annual_spend_usd)}
                  </span>
                </div>

                {/* Health Badge */}
                <div style={{ display: "flex", flexDirection: "column", gap: 5, alignItems: "flex-start" }}>
                  <span style={{
                    display: "inline-block",
                    background: badge.bg,
                    color: badge.color,
                    border: `1px solid ${badge.color}44`,
                    borderRadius: 20, padding: "3px 12px",
                    fontSize: 12, fontWeight: 600,
                    whiteSpace: "nowrap",
                  }}>
                    {badge.label}
                  </span>
                  {s.other_suppliers_count === 0 && (
                    <span style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      background: "#1f0505",
                      color: "#f97316",
                      border: "1px solid #f9731644",
                      borderRadius: 20, padding: "3px 10px",
                      fontSize: 11, fontWeight: 600,
                      whiteSpace: "nowrap",
                    }}>
                      <IconAlertTriangle size={11} color="#f97316" /> Single Source
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Category Breakdown Legend */}
        {!loading && !error && Object.keys(categoryBreakdown).length > 0 && (
          <div style={{
            background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: 12, padding: 24,
          }}>
            <h3 style={{
              margin: "0 0 16px", fontSize: 14, fontWeight: 600,
              color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em",
            }}>
              Spend by Category
            </h3>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "12px 24px" }}>
              {Object.entries(categoryBreakdown)
                .sort((a, b) => b[1] - a[1])
                .map(([cat, spend]) => (
                  <div key={cat} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{
                      width: 10, height: 10, borderRadius: "50%",
                      background: categoryColor(cat), flexShrink: 0,
                    }} />
                    <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                      {cat.replace(/_/g, " ")}
                    </span>
                    <span style={{ color: "var(--text-primary)", fontSize: 13, fontWeight: 600 }}>
                      {formatSpend(spend)}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ label, value }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered ? "var(--bg-card-hover)" : "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 12, padding: 24,
        transition: "all 0.15s ease",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 500,
            textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
            {label}
          </div>
          <div style={{ fontSize: 30, fontWeight: 700, color: "var(--text-primary)", lineHeight: 1 }}>
            {value}
          </div>
        </div>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: "var(--bg-primary)",
          border: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0,
        }}>
          {CARD_ICONS[label]}
        </div>
      </div>
    </div>
  );
}
