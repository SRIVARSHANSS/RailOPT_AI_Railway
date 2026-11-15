# RailOpt AI - demo script (T101 reference scenario)

Everything shown is **SIMULATED** on a sample corridor. RailOpt AI advises a human
controller; it does not control trains or signals.

## Start

Terminal 1 (API):

```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app
```

For demos start the API **without `--reload`**: on Windows the reload watcher can stall
and keep serving old code. Use `--reload` only while developing.

Terminal 2 (UI):

```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173** (exactly this address: the API allows it for CORS).

Notes before presenting:
- The API keeps the scenario in memory: restarting it clears events and decisions.
- The sim clock, its speed and the last optimizer result are kept in the browser tab
  (sessionStorage): a page refresh keeps them; the clock always comes back paused.
  The optimizer result is tied to the API's scenario version: after an API restart, a reset or
  a new event it is dropped automatically (within about 5 s), so no outdated recommendation lingers.
- **Demo reset** (Disruptions -> Scenario) does everything in one click: reference timetable,
  no events, no plan, session state cleared, clock at 09:55.

## Steps

1. **Login.** Pick *Controller*, then *Enter control room*. Point out the
   "demo login - real auth in Phase 8" line and the permanent SIMULATED badge.
2. **Reset.** Open *Disruptions* and click **Demo reset**. The clock goes to **09:55**.
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
   - **Optional - the time-distance chart.** Open *Timeline*. In *Planned vs actual* the solid lines
     are the simulated day: T101 goes flat inside B-C (10:03-10:18), dashed lines are the timetable.
     Switch to **Before vs after plan**: dashed = no plan (T202 and T303 wait at B, red ticks
     "wait 15" / "wait 13"), solid = accepted R1: T202 steps into the S_BC_ALT lane at B and back out
     at C, and T303 runs straight through - the lines un-bend. Hover a line for entry/exit and
     delay; click a train to follow it; scroll to zoom the time axis. (Before Accept, at 10:03, the
     same chart shows the red CRITICAL band "T202 overlap 10:13-10:28" on B-C.)
8. **T202 on the alternate line.** Press *Play* again. At **10:13** T202 leaves B and
   glides along the curved S_BC_ALT (it follows the track, it does not cut across),
   reaching C about 10:31. T101 stays stopped in B-C until 10:18 ("stopped in S_BC").
9. **Close.** *Disruptions* -> *Event history* shows E1 and "R1 accepted - REROUTE".
   Expected end state (simulated): T101 +15, T202 +4, T303 on time.

Optional: repeat step 6-7 and press *Reject* instead: a calm dismissal, the plan is
unchanged and the rejection is logged in the event history.

## Act 2: a planned maintenance block after the accepted reroute

Continue straight after step 8 of act 1 (plan R1 accepted: T202 runs on the alternate line).
Numbers below are from the simulator replay (tests/test_phase6.py prints them).

10. **Set the clock to 10:25.** On the *Traffic console*, pause and drag the scrubber (or play
    at 60x and pause) to **10:25**. T101 has just cleared B-C (10:23); T202 is on S_BC_ALT.
11. **Post the maintenance block.** *Disruptions* -> *Custom event* -> *Track closure*:
    section **S_BC**, start **10:30**, duration **20** min, *Add event* (event E2).
    - Talking point: planned maintenance is known as soon as it is posted, unlike a stoppage.
    - Talking point: nobody is inside S_BC at 10:30, so the block is allowed. (Try start 10:10:
      the form refuses it - a train is inside then - and names the first start after it clears.)
12. **Stale plan.** Back on the *Traffic console*: a glowing banner "New event since your
    accepted plan - Re-optimize", a cyan alert "New event - re-plan suggested" (E2 became
    known after R1), and a red **CRITICAL** alert "T303 closure on S_BC - planned entry 10:34,
    section closed until 10:50 (16 min short)": the detector sees the problem 9 minutes ahead.
13. **Re-optimize.** Click *Re-optimize* -> *Run optimizer at 10:25*.
    - The note says it re-plans from the current state on top of R1: T202's reroute is already
      under way and stays as it is.
    - **Keep current plan: weighted 69** - T303 is held at B until the block ends at 10:50 and
      arrives **16 min** late.
    - **Recommended: B - Reroute, weighted 59 (-10)** - "reroute T303 B->C via S_BC_ALT, hold T303
      at B until 10:36": T303 follows T202 onto the alternate line once T202 has cleared it
      (10:31 + 5 min headway) and arrives **6 min** late. CP-SAT optimal.
    - Read *Why*: "T303 is planned to enter S_BC at 10:34 while it is closed (E2) until 10:50."
14. **Accept.** *Accept plan* (R2): check, burst, back to the console. S_BC_ALT is now the
    planned route for **T202, T303**; the banner and the CRITICAL alert are gone.
    - The AI watch on T303 turns calm cyan: **"Risk reduced by plan (16 -> 2 min wait)"**.
      Talking point: under R1 T303 would have waited 16 minutes at B; under R2 it waits 2 for
      T202 to clear. Reduced, not removed - "resolved" (green) is only shown at zero wait.
15. **Play on (60x).** S_BC turns red "CLOSED" at 10:30. T303 reaches B at 10:34, waits two
    minutes at the red signal, and at **10:36** glides onto the curved alternate line behind
    T202, reaching C at 10:58. Simulated end state: T101 +15, T202 +4, T303 +6.
16. **Talking point - no invented interventions (optional).** Pause at **10:33** (T202 departs
    C then), post a *Delay* for **T202 at C, 10:33, 5 min**, and re-optimize at 10:33.
    - Every option is compared again, and the result is "No strategy improves on keeping the
      accepted plan (weighted delay 69)": T202 simply arrives 9 min late instead of 4.
    - The recommended plan is the one already in force (T303 still via S_BC_ALT at 10:36), so
      there is nothing new to do. The system says so instead of inventing an intervention.
      You can leave it without accepting.

17. **What-if (optional).** *What-if studio*: add a hypothetical *Delay* for **T303 at B, 10:34,
    20 min**, *Run what-if*: the current scenario next to the hypothetical one, with the
    HYPOTHETICAL badge. Nothing in the live scenario changes.
