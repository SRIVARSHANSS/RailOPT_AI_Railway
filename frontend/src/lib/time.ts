/** 'HH:MM' <-> minutes after midnight (display helpers only). */
export const toMin = (hhmm: string): number => {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

/** Minutes -> 'HH:MM'. A REAL replay day can run past midnight: 24:35 = 00:35 the next day. */
export const fmt = (min: number): string => {
  const m = ((Math.round(min) % 2880) + 2880) % 2880
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}
