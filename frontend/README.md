# RailOpt AI - frontend

React + TypeScript + Vite dashboard for the RailOpt AI API. All data is SIMULATED.

```powershell
npm install
npm run dev      # http://localhost:5173 (must be exactly this origin: the API's CORS allows it)
npm run build    # type-check + production build
npm run lint
```

The API must run on http://localhost:8000 (`uvicorn app.main:app --reload` from `backend/`).
Override with `VITE_API_URL`.

## Design system "Midnight Signal"

- Tokens: `src/styles/tokens.css` (CSS variables, "R G B" channels) mapped in `tailwind.config.ts`.
  Colour carries meaning: green on time, amber warning, red critical, cyan AI / recommendation,
  violet rare accent; express / passenger / freight each have a colour and always a text label.
  Contrast was computed: every text colour passes WCAG AA on every surface.
- Motion: `src/lib/motion.ts` holds every duration, easing and shared variant. Only transform and
  opacity are animated. `MotionConfig reducedMotion="user"` plus a CSS media query give final
  states and no loops for reduced motion.
- Fonts (self-hosted via @fontsource, so a projector demo works offline): Space Grotesk
  headings, Inter UI, JetBrains Mono for times and numbers.
- Components: `src/components/ui` (Button, Panel, SignalBadge, TrainChip, StatTile + CountUp,
  Skeleton, EmptyState, Toaster, Tooltip, Tabs, Dialog, AppLoader, BackgroundGrid). The
  `/design` page is the living style guide.

## Login hero media

`src/config/media.ts` lists the files; until they exist the hero shows a CSS night corridor.
With a poster image only, it drifts slowly (scale 1 -> 1.06 + slight pan over 18 s, paused for
reduced motion). With a video, it plays only on wide screens without reduced motion, fading in
over the poster once it can play through. Web files go in `public/media/`, raw sources in
`media-src/` (gitignored).

Current clip: a 13.5 s sunset railway-yard video supplied by the project owner (raw file in
`media-src/login-train-window.mp4`, origin rawpixel via Pinterest - confirm the licence before
any public use). Web copy `public/media/login-railway-sunset.mp4`: audio removed, 0.6 s fade to
dark at both ends so the loop does not jump, H.264 CRF 22, 1.06 MB, 736x414 (soft on very large
screens). The login card is see-through glass (`.login-glass`: 42 % navy + 16 px blur). Its
text contrast was measured over every frame of this clip at 1366x768: worst case 5.33:1 (AA)
with `text-ink`; `text-ink-muted` would need a 56 % tint, so the login card uses `text-ink` only.
If the clip changes, re-measure.

