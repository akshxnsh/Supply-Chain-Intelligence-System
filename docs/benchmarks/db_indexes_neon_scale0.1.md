# Index benchmark (2026-11-10T11:33:05+00:00)

- Database: PostgreSQL 18.6 (ac70818) on aarch64-unknown-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit
- Synthetic rows (scale 0.1): {'disruption_events': 30000, 'weather_alerts': 10000, 'tariff_updates': 2000, 'business_suppliers': 500, 'alternative_suppliers': 2000, 'pending_orders': 20000, 'shipment_timetable': 30000, 'completed_orders': 50000, 'supplier_reviews': 30000, 'agent_alerts': 10000, 'agent_calibration': 10000, 'inventory': 500}
- Median of 5 EXPLAIN ANALYZE runs per query, after one warm-up run
- Data is synthetic; numbers apply to this database and machine only.

| query | before (ms) | after (ms) | speed-up | seq scan before | seq scan after |
|---|---:|---:|---:|:-:|:-:|
| recent_events | 2.144 | 0.114 | 18.8x | yes | no |
| business_suppliers | 0.065 | 0.048 | 1.4x | yes | no |
| pending_orders | 1.342 | 0.059 | 22.7x | yes | no |
| alternative_suppliers | 0.251 | 0.051 | 4.9x | yes | no |
| shipments_at_risk | 2.833 | 0.156 | 18.2x | yes | no |
| recent_weather | 0.705 | 0.09 | 7.8x | yes | no |
| tariffs | 0.304 | 0.306 | 1.0x | yes | yes |
| completed_orders_many | 7.268 | 0.66 | 11.0x | yes | no |
| reviews_many | 3.65 | 0.412 | 8.9x | yes | no |
| timetable_join | 2.973 | 0.265 | 11.2x | yes | yes |
| alerts_page | 5.873 | 0.149 | 39.4x | yes | no |
| alerts_all | 3.273 | 0.092 | 35.6x | yes | no |
| suppliers_overview | 18.253 | 0.566 | 32.2x | yes | no |
| duplicate_alert | 0.691 | 0.046 | 15.0x | yes | no |
| calibration_records | 1.05 | 0.047 | 22.3x | yes | no |

Sum of all query times: 50.67 ms -> 3.06 ms (94.0% lower).
