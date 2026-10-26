# Five-minute demo script (sample data, demo clock)

All names and numbers are **sample data**. Reset the demo before going on stage
(admin: `POST /api/admin/demo/reset`; it sets the demo clock to 08:30 today).

| Time | Device | Action -> what the audience sees |
|---|---|---|
| 0:00 | Laptop (manager), clock 08:30 | `kitchen/plan.html`, today's lunch: 1,000 registered, 44 opted out -> **P50 813 / P90 862**. Cook card: rice 70.7 kg raw -> serving line 162.6 kg + **reserve vessel 9.8 kg**; sambhar with a top-up line; usual vs planned. |
| 0:40 | Phone 1 (student) | `optout.html?k=MESS1` -> hostel ID -> opted out. Laptop refresh: 45 out, **P50 812 / P90 861**, rice 162.4 kg. Tap **Issue cook card**. |
| 1:20 | Laptop, clock 11:55 -> 12:25 | `kitchen/service.html`: lid the reserve at 74 °C, 9.8 kg -> **GREEN** until 13:55. Reading 71 °C at 12:25 -> GREEN until 14:25. Tally 320. |
| 2:00 | Laptop -> Phone 2 (NGO), clock 12:30 | T-90: projected 800 -> 0 reserve diners -> 9.8 kg >= 8 kg -> **CONFIRMED**. Phone 2 shows the offer with a 10:00 countdown -> **Accept** -> laptop shows ACCEPTED, pickup 14:15. |
| 2:50 | Laptop + Phone 2, clock 14:15 | Probe 66 °C, 9.6 kg -> **Handover** -> `record.html`: 12 fields, consume by 18:15, refrigerate below 7 °C by 16:15. Phone 2 scans the QR and fills fields 10-12. Print the label. |
| 3:40 | Laptop | Yesterday's seeded batch is **RED** -> `kitchen/route.html`: reserve unsafe 6.0 kg -> BIOGAS. Cooked -> CATTLE_FEED is **blocked by the rule**. Raw vegetable trimmings 4 kg -> CATTLE_FEED is accepted. |
| 4:20 | Laptop | Dashboard: **9.6 kg rescued ≈ 23 meal equivalents (420 g)**, kg not cooked vs usual, kg by destination. "All numbers are sample data." |

## Demo-day setup

- The laptop runs everything (no venue internet needed). Turn on Windows Mobile Hotspot, connect both
  phones, set `APP_PUBLIC_BASE_URL=http://192.168.137.1:8000` so the QR opens on the phones.
- `docker compose up -d db`, then
  `.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` (one worker, no `--reload`).
- Allow Python through the firewall on private networks beforehand.
- Keep the backup video on a USB drive and a phone, and a printed record ready.

Pages marked in this script arrive phase by phase (see README "Build phases"). Never demo a feature
that is not built.
