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
