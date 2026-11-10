# Index benchmark (2026-11-10T11:17:21+00:00)

- Database: PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
- Synthetic rows (scale 1.0): {'disruption_events': 300000, 'weather_alerts': 100000, 'tariff_updates': 20000, 'business_suppliers': 5000, 'alternative_suppliers': 20000, 'pending_orders': 200000, 'shipment_timetable': 300000, 'completed_orders': 500000, 'supplier_reviews': 300000, 'agent_alerts': 100000, 'agent_calibration': 100000, 'inventory': 5000}
- Median of 7 EXPLAIN ANALYZE runs per query, after one warm-up run
- Data is synthetic; numbers apply to this database and machine only.

| query | before (ms) | after (ms) | speed-up | seq scan before | seq scan after |
|---|---:|---:|---:|:-:|:-:|
| recent_events | 62.235 | 1.292 | 48.2x | yes | no |
| business_suppliers | 0.641 | 0.029 | 22.1x | yes | no |
| pending_orders | 30.465 | 0.09 | 338.5x | yes | no |
| alternative_suppliers | 3.7 | 0.05 | 74.0x | yes | no |
| shipments_at_risk | 34.697 | 0.19 | 182.6x | yes | no |
| recent_weather | 12.775 | 0.678 | 18.8x | yes | no |
| tariffs | 7.338 | 8.629 | 0.9x | yes | yes |
| completed_orders_many | 66.16 | 2.297 | 28.8x | yes | no |
| reviews_many | 50.023 | 1.978 | 25.3x | yes | no |
| timetable_join | 45.229 | 3.287 | 13.8x | yes | yes |
| alerts_page | 191.727 | 1.422 | 134.8x | yes | no |
| alerts_all | 41.056 | 0.097 | 423.3x | yes | no |
| suppliers_overview | 497.279 | 1.12 | 444.0x | yes | no |
| duplicate_alert | 15.564 | 0.052 | 299.3x | yes | no |
| calibration_records | 20.612 | 0.171 | 120.5x | yes | no |

Sum of all query times: 1079.5 ms -> 21.38 ms (98.0% lower).
