import { useState, useEffect } from "react";

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

function healthBadge(spend) {
  if (spend > 400_000) return { label: "Healthy", color: "#22c55e", bg: "#052e16" };
  if (spend >= 100_000) return { label: "Monitor", color: "#eab308", bg: "#1c1a05" };
  return { label: "At Risk", color: "#ef4444", bg: "#1f0505" };
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
      marginLeft: "var(--sidebar-width)",
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
            { label: "Total Suppliers", value: suppliers.length, icon: "🏭" },
            { label: "Total Annual Spend", value: formatSpend(totalSpend), icon: "💰" },
            { label: "Countries", value: uniqueCountries, icon: "🌐" },
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
            gridTemplateColumns: "2fr 1.2fr 1fr 1.6fr 100px",
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
            const badge = healthBadge(s.annual_spend_usd);
            const barPct = Math.max(4, (s.annual_spend_usd / maxSpend) * 100);
            const isHovered = hoveredRow === i;
            return (
              <div
                key={i}
                onMouseEnter={() => setHoveredRow(i)}
                onMouseLeave={() => setHoveredRow(null)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "2fr 1.2fr 1fr 1.6fr 100px",
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
                <div>
                  <span style={{
                    display: "inline-block",
                    background: badge.bg,
                    color: badge.color,
                    border: `1px solid ${badge.color}44`,
                    borderRadius: 20, padding: "3px 10px",
                    fontSize: 12, fontWeight: 600,
                  }}>
                    {badge.label}
                  </span>
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

function SummaryCard({ label, value, icon }) {
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
        <div style={{ fontSize: 24, opacity: 0.8 }}>{icon}</div>
      </div>
    </div>
  );
}
