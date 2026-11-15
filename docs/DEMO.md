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
8. **T202 on the alternate line.** Press *Play* again. At **10:13** T202 leaves B and
   glides along the curved S_BC_ALT (it follows the track, it does not cut across),
   reaching C about 10:31. T101 stays stopped in B-C until 10:18 ("stopped in S_BC").
9. **Close.** *Disruptions* -> *Event history* shows E1 and "R1 accepted - REROUTE".
   Expected end state (simulated): T101 +15, T202 +4, T303 on time.

Optional: repeat step 6-7 and press *Reject* instead: a calm dismissal, the plan is
unchanged and the rejection is logged in the event history.

## Optional second act: a new event after the accepted plan

Continue straight after step 8 (T202 is on the alternate line, plan R1 accepted).

10. **Play to 10:33** (60x, or scrub). Under R1, T202 departs C at 10:33.
11. **Inject the delay.** *Disruptions* -> *Custom event* -> *Delay*: train **T202**, station
    **C**, start **10:33**, **5 min**, *Add event*. It becomes event E2.
    - Talking point: try a *Track closure* on **S_CD at 10:45** first. The form refuses it
      inline: "T202 is inside S_CD at 10:45; closing an occupied section isn't modelled -
      choose a start after it clears (11:16)". The model never strands a train.
12. **Stale plan.** Back on the *Traffic console* at 10:33: a glowing banner "New event since
    your accepted plan - Re-optimize" and a cyan alert "New event - re-plan suggested"
    (E2 became known after R1).
13. **Re-optimize.** Click *Re-optimize* -> *Run optimizer at 10:33*. A note says the run
    re-plans from the current state on top of R1: trips already started (T202 on S_BC_ALT)
    stay as R1 made them; the baselines now mean "keep the current plan".
    - Simulated result on the reference timetable: every strategy ties at weighted 63
      (T101 +15, T202 +9, T303 on time); the recommendation says no strategy improves on
      keeping the accepted plan. Say so plainly: the system does not invent an improvement.
14. **Accept.** Accept R2: the banner disappears, S_BC_ALT is still T202's route, and the
    event history shows "R2 accepted" (the API logs that it replaced R1).
15. **What-if (optional).** Open *What-if studio*, add a hypothetical *Delay* for **T303 at B,
    10:34, 20 min**, *Run what-if at 10:33*: current weighted 63 next to hypothetical 83, with
    the HYPOTHETICAL badge. Nothing in the live scenario changes.
