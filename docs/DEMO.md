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

Open **http://localhost:5173** (exactly this address: the API allows it for CORS, with cookies).

### Before presenting: demo users (once)

The database must be migrated (`python -m alembic upgrade head`, README). Create one user per role
from `backend/`; each command asks for the password at a hidden prompt (at least 10 characters):

```powershell
python -m app.cli create-admin --email admin@demo.local --name "Demo Admin"
python -m app.cli create-user --email controller@demo.local --name "Demo Controller" --role CONTROLLER
python -m app.cli create-user --email analyst@demo.local --name "Demo Analyst" --role ANALYST
python -m app.cli list-users
```

Keep the passwords somewhere private (never in the repository or on a slide). Five wrong
passwords for one email within 15 minutes lock it for 15 minutes, so type carefully on stage;
an admin can reset a password on *Users*.

Notes before presenting:
- The scenario is stored in PostgreSQL: restarting the API keeps events, the accepted plan and the
  decision log (and the scenario version). **Demo reset** starts a clean scenario.
- The sim clock, its speed and the last optimizer result are kept in the browser tab
  (sessionStorage): a page refresh keeps them; the clock always comes back paused.
  The optimizer result is tied to the API's scenario version: after an API restart, a reset or
  a new event it is dropped automatically (within about 5 s), so no outdated recommendation lingers.
- The API starts on the REAL recorded day (DG -> MDU, 2024-09-12, label REAL). Acts 1-2 use the
  SIMULATED corridor, so step 2 (Demo reset) switches to it; Act 3 loads the real day again.
- **Demo reset** (Disruptions -> Scenario) does everything in one click: reference timetable,
  no events, no plan, session state cleared, clock at 09:55.

## Steps

1. **Login.** Sign in as the **controller** demo user. Point out the user and the *Controller*
   role in the top bar and the permanent data badge. Talking point: an analyst sees the same
   screens but the optimizer and accept buttons are disabled ("Needs the Controller role"); the API
   refuses those calls too (403), and every sign-in and every decision is in the audit log.
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
   - Read the explanation (every sentence is a template filled from the API's numbers, no LLM):
     *Reason* (the rule-based clash: "T202 ... clashes because T101 holds it until 10:28"),
     *What we recommend*, *Counterfactual* (no re-planning: 88 weighted, T101 15 / T202 15 /
     T303 13 min), *Expected impact* (T202 15 -> 4, T303 13 -> 0 min).
   - **Talking point - read the "Why not the others?" line aloud:** *"HOLD: weighted delay 88,
     35 more than REROUTE"* - and COMBINED reaches the same 53 but ties go to the simpler strategy.
     Then *Constraints respected* (the replay has 0 violations), *Assumptions this depends on*
     (headway per section, priority weights) and *Confidence* (CP-SAT OPTIMAL for the REROUTE model).
   - *Copy explanation* puts the whole explanation on the clipboard as plain text for a report.
   - On the console the alerts now list the model's top drivers: "Model risk raised by: it is
     planned to enter 10 min before the section clears", "it uses S_BC, a single-track
     section". They explain the model's score, not
     the cause; the cause is the rule-based Reason line.
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

## Optional: the results (Analytics and Model Insights)

18. **Analytics.** Open *Analytics*. Everything here is read from the stored evaluation
    (`eval/reports/eval_summary.json`), checked against the files it was computed from.
    - Point out the setup tiles (scenarios, disruptions, 0 overlap with the training data, 0 violations)
      and the bar chart with 95% CI whiskers; switch *Deterministic* / *Robustness*.
    - Talking point: dynamic re-planning beats no re-planning on most scenarios and is never claimed
      "optimal" beyond what CP-SAT proved (the solver panel shows the OPTIMAL count).
    - Read the purple conclusion under *ML integration variants* out loud: the ML gives early
      warning, but feeding its risk into the optimizer did not improve plans. That is a result,
      not a failure, and the variants were pre-registered.
    - The *Limits* box: simulated, plans frozen in the robustness replays, holds count as waits.
19. **Model Insights.** Open *Model insights*: baselines vs models, the equal-precision
    head-to-head (model recall vs the rule's at the same precision), the ablation without the rule
    flag, global SHAP importance, and the note that with 10% of the data the model did not beat
    the rule.
    - If either page shows **Outdated - rerun**, a result file or model changed since the run:
      run the command it names (from `backend/`) before presenting.


## Act 3: Real day replay - Dindigul to Madurai, Thursday 12 Sept 2024

REAL recorded running times (RSTGCN dataset, Sept 2024, CC BY-SA 4.0; docs/DATA_SOURCES.md).
The top badge turns green "Real data"; once an event is added it turns violet "Hypothetical".
Numbers quoted below come from the API on our run; read them from the screen, not from here.

20. **Load the day.** *Disruptions* -> *Scenario* -> *Real day replay*: keep **2024-09-12 Thu -
    22 trains (demo day)** and click *Load real day*. The clock jumps to **08:30**.
21. **The console.** *Traffic console*: title "Dindigul - Madurai (DG -> MDU)", the green banner
    reads **"REAL RECORDED MOVEMENTS - 2024-09-12 - RSTGCN Sept 2024 (CC BY-SA 4.0)"**. Say: trains
    move by their recorded times; between recorded stations positions are interpolated (dashed ring,
    "(interpolated)" in the train list). Live alerts: no alert; a grey line lists possible clashes
    that rest on interpolated times (uncertain, not alerts).
22. **Play at 60x and point out the real overtake.** 16343 Amritha left DG at 08:15, 22627 at 08:38;
    22627 reached Madurai at 09:33, 16343 at 10:00. Where it was overtaken is not recorded: the
    replay places 16343's wait at the KQN loop (interpolated). Talking point: a train can only be
    overtaken where a loop is free - at Koodal Nagar (no loop, ASSUMED) it never happens.
23. **Inject a hypothetical stoppage.** Pause, set the clock to **08:53** (scrubber). *Disruptions*
    -> preset card "Real day replay (hypothetical event)": **22627 stops in ABI-KQN at 08:53 for
    25 min** -> *Inject event*. The badge turns violet: "HYPOTHETICAL on a real recorded day".
24. **HOLD vs RESEQUENCE.** *Strategy comparison* -> *Run optimizer at 08:53*. Point out:
    - only Hold and Resequence are offered; "Not offered: Reroute, Combined - no alternate line";
    - priorities are ASSUMED (premium 1, superfast 2, express 3);
    - on our run Hold matches no re-planning (weighted 128): 16343 waits at KQN for 22627;
      Resequence (recommended, 120) lets 16343 go on and be overtaken at the VDP loop instead;
    - the headway note: the same recommendation and ranking with a 4 min headway, where Resequence
      only ties no re-planning (156 vs 156) - the gain depends on the calibrated headway;
    - read "Why not the others?" aloud: *"HOLD: weighted delay 128, 8 more than RESEQUENCE"*, and
      REROUTE / COMBINED "not offered here" (no alternate line). *Assumptions this depends on*
      lists headway 0 CALIBRATED, the ASSUMED loops and priorities; *Confidence* ends with "Same
      recommendation and ranking at headway 4 min as at 0 min. At headway 4 min the gain
      disappears: RESEQUENCE 156 vs NO_REPLANNING 156" - say it plainly: the advantage rests on
      the calibrated headway;
    - the console has no model drivers on this day: the ML models are off on REAL data and the
      model note says so.
25. **Accept and read the label aloud.** *Accept plan*. Back on the console the banner says
    "HYPOTHETICAL on a real recorded day: recorded until 08:53, simulated after it". Read it aloud:
    *"Everything before 08:53 is what really happened on 12 September 2024; everything after is a
    hypothetical simulation of a stoppage that did not happen. RailOpt AI advises; it controls
    nothing."* The *Timeline* shows the same label and the before / after plan lines.

## Optional: administration (sign in as the admin demo user)

1. **Users.** *Users* lists the three demo users with their role, status and last sign-in. Change
   the analyst's role and back; show that the change ends that user's open session. Open the
   **audit log**: the controller's LOGIN, EVENT_ADDED, SCENARIO_RESET and DECISION entries from
   the acts above, each with the user and the time. Filter it by action (e.g. DECISION).
2. **Network.** *Network* shows four corridors. *Reference* and *Full day* are read-only (the
   tests, the demo numbers and the evaluation depend on those files). *Real DG-MDU* is read-only
   with its sources and licence (DERIVED / ASSUMED / CALIBRATED columns). *Custom* is editable:
   type an invalid value (e.g. a negative km) and *Save*: the API lists the problem by row and
   column and saves nothing. *Import CSV* works the same way per table. A valid custom corridor
   can be run with Disruptions -> Reset -> *Custom* (SIMULATED; the ML models are not applied to it).
3. **Audit log export.** *Reports* -> *Audit log CSV* (optionally one action, e.g. DECISION): every
   row with user, time and IP. Exports are themselves logged (REPORT_EXPORTED).

## Optional: Conflicts and Alerts, Reports (after Act 1 or Act 2)

1. **Conflicts and alerts** (controller). Open *Conflicts & alerts* with the clock after the
   accepted plan (e.g. 10:30). The tiles count rule-based conflicts, uncertain clashes (real days
   only), the ML watchlist and closures at the clock; click a tile to filter, or filter by
   severity, type, train, section, or search a train number.
   - *History*: the T202 overlap on S_BC **appeared at 10:03** ("E1 (STOPPAGE, T101) became
     known") and **cleared at 10:05** ("plan R1 (REROUTE) accepted by" the controller). Talking
     point: the backend re-runs the same detector minute by minute with what was known then; the
     UI types nothing.
   - *Show on map* opens the console with S_BC highlighted; *Show on timeline* selects the train.
   - *Acknowledge* an alert: it stays visible, dimmed, with who acknowledged it; the analyst sees
     the button disabled ("Needs the Controller role"). The audit log has ALERT_ACKNOWLEDGED.
2. **Reports** (controller: scenario report; analyst or admin: all).
   - *Scenario report PDF / CSV* at the clock: label, version, sim time, who generated it and when;
     events, conflicts, alert history, every recommendation with its full explanation, decisions
     with who took them, per-train delays, the time-distance chart. Every page footer carries the
     data label (REAL / HYPOTHETICAL on a real recorded day in Act 3).
   - *Evaluation PDF* (analyst): the Analytics numbers, charts, ML-variants conclusion and limits.
     If the result files changed, the button is disabled and the page says "Outdated - rerun ...".
   - *Model PDF*: the synthetic model card (footer SIMULATED) and the real-data card (footer REAL).
