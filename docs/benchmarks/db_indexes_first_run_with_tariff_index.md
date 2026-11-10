# Index benchmark (2026-11-10T11:14:42+00:00)

- Database: PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
- Synthetic rows (scale 1.0): {'disruption_events': 300000, 'weather_alerts': 100000, 'tariff_updates': 20000, 'business_suppliers': 5000, 'alternative_suppliers': 20000, 'pending_orders': 200000, 'shipment_timetable': 300000, 'completed_orders': 500000, 'supplier_reviews': 300000, 'agent_alerts': 100000, 'agent_calibration': 100000, 'inventory': 5000}
- Median of 7 EXPLAIN ANALYZE runs per query, after one warm-up run
- Data is synthetic; numbers apply to this database and machine only.

| query | before (ms) | after (ms) | speed-up | seq scan before | seq scan after |
|---|---:|---:|---:|:-:|:-:|
| recent_events | 25.207 | 2.168 | 11.6x | yes | no |
| business_suppliers | 0.365 | 0.052 | 7.0x | yes | no |
| pending_orders | 19.633 | 0.128 | 153.4x | yes | no |
| alternative_suppliers | 3.105 | 0.063 | 49.3x | yes | no |
| shipments_at_risk | 23.963 | 0.321 | 74.7x | yes | no |
| recent_weather | 8.528 | 1.075 | 7.9x | yes | no |
| tariffs | 4.775 | 12.084 | 0.4x | yes | no |
| completed_orders_many | 55.237 | 2.609 | 21.2x | yes | no |
| reviews_many | 42.048 | 2.072 | 20.3x | yes | no |
| timetable_join | 27.963 | 3.808 | 7.3x | yes | yes |
| alerts_page | 159.825 | 1.81 | 88.3x | yes | no |
| alerts_all | 36.934 | 0.123 | 300.3x | yes | no |
| suppliers_overview | 349.874 | 1.374 | 254.6x | yes | no |
| duplicate_alert | 11.916 | 0.059 | 202.0x | yes | no |
| calibration_records | 16.388 | 0.243 | 67.4x | yes | no |

Sum of all query times: 785.76 ms -> 27.99 ms (96.4% lower).
