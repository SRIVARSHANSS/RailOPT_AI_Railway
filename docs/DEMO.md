# RailOpt AI - demo script (T101 reference scenario)

Everything shown is **SIMULATED** on a sample corridor. RailOpt AI advises a human
controller; it does not control trains or signals.

## Start

Terminal 1 (API):

```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

Terminal 2 (UI):

```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173** (exactly this address: the API allows it for CORS).

Notes before presenting:
- The API keeps the scenario in memory: restarting it clears events and decisions.
- The sim clock and the last optimizer result live in the browser tab: a page refresh
  sets the clock back to 09:55 and clears the comparison (the API scenario stays).
- If the API was edited while running and stops answering with new fields, restart it
  (on Windows the `--reload` watcher occasionally stalls).

## Steps

1. **Login.** Pick *Controller*, then *Enter control room*. Point out the
   "demo login - real auth in Phase 8" line and the permanent SIMULATED badge.
2. **Reset.** Open *Disruptions*, choose *Reference (3 trains)*, *Reset scenario*,
   confirm. The clock goes to **09:55**.
3. **Console at 09:55.** Open *Traffic console*. T101 is at B, T202 runs on the
   double-track A-B, T303 has not started. KPIs: 0 conflicts.
4. **Inject the event.** Open *Disruptions*, click *Inject event* on the card
   "T101 stops in B-C at 10:03 for 15 min". Red flash, toast "Event E1 injected ...
   known to the console from 10:03".
   - Talking point: a stoppage is a surprise. The console only learns about it at 10:03,
     the same no-leakage rule the ML model was trained with.
5. **Run the clock.** Back to *Traffic console*, speed **60x**, press *Play*. Pause at
   **10:03** (or drag the scrubber: a jump snaps the trains, it never glides).
   - A **CRITICAL** alert appears: "T202 overlap on S_BC - planned entry 10:13, T101 holds
     it until 10:28 (15 min short, in 10 min) - model 98%". It pulses red.
   - Click it: S_BC turns red and T101 / T202 are outlined; everything else dims.
   - **Talking point - the amber AI watch on T303:** "The rules miss it, the model flags
     0.88." T303 has no direct conflict in the planned view, but the model has learned the
     knock-on: if nothing is re-planned, T303 waits 13 min behind T202.
6. **Strategy comparison.** Open *Strategies*, click *Run optimizer at 10:03*.
   - Six cards: two baselines and four CP-SAT strategies, each with its status badge
     ("CP-SAT optimal" only when the solver proved it), weighted / total delay,
     per-train delay bars, throughput and actions. All numbers come from replaying each
     plan through the simulator.
   - **B - Reroute** glows as *Recommended*: "reroute T202 B->C via S_BC_ALT".
     Animated bars: **weighted 88 -> 53**, total 43 -> 19 min.
   - Read the explanation cards: *Why* (the detected conflict), *If we do nothing*
     (no re-planning: 88 weighted, T101 15 / T202 15 / T303 13 min), *Expected impact*.
7. **Accept.** Click *Accept plan*: the button turns into a check with a small burst,
   a toast confirms, and the app wipes back to the console.
   - The alternate line is now labelled "planned route for T202" (dashed cyan).
   - **Talking point:** the AI watch on T303 has turned **green and struck through -
     "Risk resolved by accepted plan"** (in the accepted plan's replay T303 waits 0 min).
     The CRITICAL alert is gone because the detector now plans with the reroute.
8. **T202 on the alternate line.** Press *Play* again. At **10:13** T202 leaves B and
   glides along the curved S_BC_ALT (it follows the track, it does not cut across),
   reaching C about 10:31. T101 stays stopped in B-C until 10:18 ("stopped in S_BC").
9. **Close.** *Disruptions* -> *Event history* shows E1 and "R1 accepted - REROUTE".
   Expected end state (simulated): T101 +15, T202 +4, T303 on time.

Optional: repeat step 6-7 and press *Reject* instead: a calm dismissal, the plan is
unchanged and the rejection is logged in the event history.
