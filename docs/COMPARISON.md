# MENDORA — comparison with the second project (mendora-ai__2_) and what was merged

Base kept: **our project**. It has a real database (SQLite + SQLAlchemy), Argon2 password hashing, a much larger test
suite, a stricter safety engine and honest labelling. Features the second project had and ours didn't were added below
— rebuilt to our rules, not copied.

## Added from the second project (improved)

| Feature | Second project | What we built |
| --- | --- | --- |
| **Admin dashboard** | Stats, verification queue, safety escalations | `/admin`: stats, technician verification (written note required), repair-case verification, high-risk report list (contact details hidden), system status |
| **Reviews / ratings** | Any customer could rate *any* technician ID sent in the request; all feedback listed to any user | Only the booking's own customer, only after **completion**, once per booking; technician taken from the booking; comments have contact details removed; reviewer shown as "A MENDORA customer" |
| **Estimate + approval** | Technician estimate; customer approval | Technician sends labour + materials after accepting; **payment is blocked until the customer approves**; can decline and get a new estimate; locked once paid |
| **Commission breakdown** | Decimal pricing with platform fee | Same idea, Decimal-safe; shown as sandbox (nothing is collected) |
| **Escrow** | Escrow wording | Sandbox payment is **held** until the job is completed, then **released** (simulated); refunded → **returned** |
| **Photo attachments** | Upload of issue attachments | JPEG/PNG/WebP checked by content, **GPS/camera metadata removed**, 3 per request, visible only to owner, admins and a technician **after they accept**; never sent to the AI |
| **Map + distance** | Leaflet map, exact GPS haversine distance | Leaflet map, but only **approximate area centres** — "about X km between area centres"; never "nearest"; sorting still by service area |
| **Knowledge browse page** | Knowledge repository page | `/guides`: search/browse; shows causes and warnings, **no DIY steps** (those still need the safety check) |
| **Backup** | Snapshot utility for CSV files | `python -m app.cli backup` — safe SQLite backup + photos |

## Not adopted (and why)

| Second project | Reason |
| --- | --- |
| CSV files as the database | Ours uses a real database with constraints (e.g. no double-booking, one successful payment per booking) |
| Seeded "Verified" technicians with real-sounding names | Presents demo data as real, verified professionals. Ours are labelled "Demo sample — not a real technician" |
| Demo passwords in the README + one-click login buttons | Shares credentials; ours creates accounts with passwords you choose |
| Payment success auto-accepts a booking | Bypasses the technician's decision |
| Admin can force any booking status | Bypasses the status rules |
| "Deterministic fallback" in place of AI diagnosis | Ours never presents fallback text as a diagnosis; guides are labelled as guides |
| PBKDF2 password hashing | Ours uses Argon2 (stronger) |

## Already in both (kept ours)

Safety engine before AI, Nebius/OpenAI-compatible AI client, Tavily web research, sandbox payments, Docker + nginx,
JWT auth with production secret checks, in-app notifications, technician verification by admins.

> ⚠️ The uploaded second-project zip contains a real `.env` file (with a Tavily API key and an admin password).
> Don't share that zip; rotate the Tavily key if it was shared.
