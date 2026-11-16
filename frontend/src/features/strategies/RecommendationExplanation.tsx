import { BadgeCheck, ClipboardCopy, Gauge, GitCompareArrows, Lightbulb, ListChecks, ShieldCheck, Undo2, Wrench } from 'lucide-react'
import { useState } from 'react'
import type { Explanation } from '../../api/types'
import { cn } from '../../lib/cn'
import { toast } from '../../store/toast'

/** Phase 7 recommendation explanation. The UI types no sentence and no number: every line is the
 *  API's template text (backend/app/services/explainer), shown in the order Reason -> What we
 *  recommend -> Counterfactual -> Expected impact -> Why not the others -> Constraints ->
 *  Assumptions -> Confidence. "Copy explanation" copies the API's plain_text. */
export function RecommendationExplanation({ e }: { e: Explanation }) {
  return (
    <div className="mt-6 space-y-3">
      <div className="grid gap-3 lg:grid-cols-2">
        <Part icon={<Lightbulb className="h-4 w-4" />} title="Reason">{e.reason}</Part>
        <Part icon={<Wrench className="h-4 w-4" />} title="What we recommend">{e.recommend}</Part>
        <Part icon={<Undo2 className="h-4 w-4" />} title="Counterfactual">{e.counterfactual}</Part>
        <Part icon={<Gauge className="h-4 w-4" />} title="Expected impact">
          {e.expected_impact}
          {e.per_train.length > 0 && (
            <ul className="mt-2 space-y-0.5 font-mono text-sm text-ink-muted">
              {e.per_train.map((p) => <li key={p.train_id}>{p.text}</li>)}
            </ul>
          )}
        </Part>
      </div>

      <Part icon={<GitCompareArrows className="h-4 w-4" />} title="Why not the others?">
        <ul className="space-y-1">
          {e.why_not.map((w) => (
            <li key={w.name} className={cn(w.kind === 'unavailable' && 'text-ink-muted')}>{w.text}</li>
          ))}
        </ul>
      </Part>

      <div className="grid gap-3 lg:grid-cols-2">
        {e.constraints && (
          <Part icon={<ShieldCheck className="h-4 w-4" />} title={e.constraints.respected ? 'Constraints respected' : 'Constraints'}
            tone={e.constraints.respected ? 'good' : 'bad'}>
            <p>{e.constraints.summary}</p>
            <ul className="mt-1.5 space-y-0.5 text-sm text-ink-muted">
              {e.constraints.items.map((t) => <li key={t} className="flex gap-1.5"><BadgeCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-signal-green" aria-hidden />{t}</li>)}
            </ul>
          </Part>
        )}
        <Part icon={<ListChecks className="h-4 w-4" />} title="Assumptions this depends on">
          <ul className="space-y-1 text-sm">
            {e.assumptions.map((a) => (
              <li key={a.name}>
                <span className="mr-1.5 rounded border border-signal-amber/40 px-1 font-mono text-[0.68rem] text-signal-amber">{a.label}</span>
                {a.text}
              </li>
            ))}
          </ul>
        </Part>
      </div>

      <p className="text-sm text-ink-muted"><span className="font-semibold text-ink">Confidence: </span>{e.confidence} {e.note}</p>
      {e.plain_text && <CopyExplanation text={e.plain_text} />}
    </div>
  )
}

function Part({ icon, title, tone, children }: { icon: React.ReactNode; title: string; tone?: 'good' | 'bad'; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-line/15 bg-canvas-0/40 p-4">
      <h3 className={cn('flex items-center gap-2 text-sm font-semibold uppercase tracking-wider',
        tone === 'bad' ? 'text-signal-red' : tone === 'good' ? 'text-signal-green' : 'text-signal-cyan')}>{icon}{title}</h3>
      <div className="mt-2 text-ink">{children}</div>
    </section>
  )
}

/** Copies the API's plain_text. Clipboard can be blocked: fall back to execCommand, then to
 *  showing the text selected so the controller can copy it by hand. */
function CopyExplanation({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      toast({ tone: 'success', title: 'Explanation copied', description: 'Plain text, ready for a report.' })
      return
    } catch { /* fall through */ }
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.setAttribute('readonly', '')
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(ta)
      if (ok) {
        toast({ tone: 'success', title: 'Explanation copied', description: 'Plain text, ready for a report.' })
        return
      }
    } catch { /* fall through */ }
    setOpen(true)
    toast({ tone: 'info', title: 'Clipboard blocked', description: 'The text is shown below: select it and copy.' })
  }
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={copy}
          className="inline-flex items-center gap-2 rounded-lg border border-line/25 px-3 py-1.5 text-sm font-semibold text-ink hover:bg-white/[0.05] focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-cyan">
          <ClipboardCopy className="h-4 w-4" aria-hidden />Copy explanation
        </button>
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
          className="text-sm text-ink-muted underline-offset-2 hover:underline">{open ? 'Hide plain text' : 'Show plain text'}</button>
      </div>
      {open && (
        <textarea readOnly value={text} rows={12} aria-label="Explanation as plain text"
          onFocus={(ev) => ev.currentTarget.select()}
          className="mt-3 w-full rounded-lg border border-line/20 bg-canvas-0/60 p-3 font-mono text-xs text-ink" />
      )}
    </div>
  )
}
