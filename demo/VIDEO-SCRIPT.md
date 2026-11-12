# Demo video script — "SiteBefore, settled by a verified agent"

**Target runtime: 2:30–2:50 (hard cap: under 3:00 — judges are not required to watch past 3 minutes).**
**Format:** terminal screen capture of `python3 demo/demo_flow.py`, run live, with voiceover. No music (rules bar copyrighted music; use none or a self-made tone). Every amount on screen is a sandbox DEMO amount in CAD — the demo prints that label itself. The run also names its example client on screen — **Shenail Hair Salon & Nail Bar (shenailhairlounge.ca), Niagara Falls, SiteBefore's family pilot client** — directly above a printed SIMULATED-scenario label; both stay in frame (see recording notes).
**Capture assets already produced:** `demo/demo_flow.py` (the surface) and `demo/demo-transcript.txt` (a verified full run, exit 0 — use it to rehearse timing; re-run live for the recording).

---

## Shot list

**Persistent screen bug (from 0:00, every shot):** a small corner label reading "SIMULATED — in-memory run · DEMO amounts (CAD)" stays on screen for the entire video, so the simulated state is disclosed even in the cold-open's first frames and in any scrubbed still. It never overlaps the verdict lines.

| # | Time | Screen | Voiceover (approx.) |
|---|------|--------|---------------------|
| 1 | 0:00–0:10 | **Cold-open:** terminal already running — the S2 verdict lines land on screen: "expected $99, attempted $999 — CONFLICTED — HELD. No order created. Nothing captured." At ~0:05 a plain-text title overlay fades in over the terminal (not a separate card): "SiteBefore, settled by a verified agent — a PayPal AI Hackathon entry by Mission Winning" | "Month two. The billing agent just tried to charge nine hundred dollars too much. This is the gate that stopped it." |
| 2 | 0:10–0:30 | Terminal: the run restarts from the top; the example-client panel (Shenail Hair Salon & Nail Bar — family pilot client; SIMULATED label visible) and the approved quote panel (Website Build $900, Care Plan $99, DEMO label visible) | "SiteBefore is an agent-run website service, and its billing agent drafts the charges. Everything is graded against one document: the quote approved for our family pilot client's job — Shenail Hair Salon and Nail Bar, a real salon in Niagara Falls. Build nine hundred, care plan ninety-nine a month. The scenario is simulated — no real money moves." |
| 3 | 0:30–0:55 | Scene 1: S1 verdict lines + CAPTURED, order + capture ids | "The salon's first payment, exactly as quoted. The comparator grades every claim — payee, currency, each line, the total. Corroborated. The gate lets the runner settle it through PayPal." |
| 4 | 0:55–1:30 | Scene 2 (the cold-open scene, in full): S2 CONFLICTED verdict — the Build line flagged "not in evidence for this charge", amount "expected $99, attempted $999" — then HELD, orders/captures counters unchanged | "Month two of the care plan. The agent drafts the full nine ninety-nine again — repeating the one-time build fee. Expected ninety-nine, attempted nine ninety-nine. Conflicted. Held. No order was created. Nothing was captured. The agent cannot talk its way past the hold." |
| 5 | 1:30–1:50 | Scene 2 continued: queue entry REJECTED; corrected $99 draft → CORROBORATED → CAPTURED | "A human rejects the held draft. The agent re-drafts at ninety-nine, it's graded fresh — and settles." |
| 6 | 1:50–2:08 | Scene 3 + 4, quick: S3 wrong payee HELD; S4 unquoted add-on PARTIAL → HELD | "Same gate, two more shapes: right amount to the wrong payee — held. An add-on nobody quoted bundled into the charge — held." |
| 6.5 | 2:08–2:18 | **Fails closed, verifiably:** the toolkit client tests running green (11 passed), then the live client constructed without credentials printing its refusal. On-screen caption: "No credentials → the live client refuses to run. Correct behaviour." | "And the live PayPal client never fakes a success: without sandbox credentials it refuses to run at all. That's the same fail-closed rule, on the real integration." |
| 7 | 2:18–2:45 | Ledger panel: 2 orders, 2 captures, 3 drafts held, $0 captured from held drafts; closing lines on screen, including the simulated-scenario note | "Two verified charges settled. Three bad drafts stopped, capturing zero dollars. The gate has no execute path — capture happens only on a verified verdict. Both charges were simulated, for our pilot client's example job. That's SiteBefore, settled by a verified agent." |

**Shot 6.5 branch (pre-decided — do not fork this at recording time):** if a live S1 sandbox capture exists by recording time, it replaces the test-run footage in shot 6.5, and the fail-fast refusal stays as a ~3-second on-screen card inside the same beat ("…and without credentials, the same client refuses to run"). The branch is chosen the moment the credential question resolves (cutoff: credentials in hand by 12:00 pm ET), never at the recording session.

## Recording notes

- Run the demo live in the capture (`cd paypal-build && python3 demo/demo_flow.py`); it needs nothing but Python 3 — no install, no network, no credentials — because the demo client is the in-memory implementation of the same Orders contract. Say so if asked; the README states it plainly too.
- For the cold-open (shot 1), capture the S2 verdict block from a full run and place it first; the run then restarts on camera at shot 2. The persistent SIMULATED bug (see shot list) is on screen from frame one — do not record any take without it.
- Keep the terminal font large (the verdict detail lines are the product — they must be readable at 720p).
- Do not crop or scroll past the example-client / SIMULATED panel in shot 2 — the family-pilot disclosure is part of the entry, not a disclaimer to hide. Before uploading, check the disclosure text and the bug are legible at phone size and never overlap the verdict lines.
- Pause ~1s on each verdict block; the script's scene banners are the natural chapter breaks.
- End card: repo URL + "Built with PayPal's agent toolkit (Apache-2.0, vendored) · MIT" — fill the repo URL in once the public repo exists.
- Upload as **public** on YouTube (rules require publicly visible, <3 min) and paste the link into the Devpost form and `SUBMISSION-PACK.md`.
