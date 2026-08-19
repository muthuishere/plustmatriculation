/**
 * Charts, hand-rolled in SVG.
 *
 * Palette, mark specs and the accessibility rules follow the data-viz method:
 * categorical hues assigned in fixed order and never cycled, one axis, thin
 * marks with rounded data-ends, a 2px surface gap between stacked segments,
 * recessive grid, hover tooltips, and direct labels — the last is not optional
 * here: three of the light-mode hues sit under 3:1 against the light surface,
 * so the values must be readable as text, not inferred from colour.
 *
 * Palette validated with the skill's checker in both modes:
 *   light  worst adjacent CVD ΔE 9.1, normal-vision 19.6
 *   dark   worst adjacent CVD ΔE 8.4, normal-vision 19.3
 */
import { useState, type ReactNode } from 'react'

export const SUBJECT_ORDER = ['physics', 'chemistry', 'maths', 'biology', 'botany', 'zoology']

/** Fixed slot per subject — the colour follows the entity, never its rank, so
 *  filtering the set never repaints the survivors. */
export const SUBJECT_SLOT: Record<string, number> = Object.fromEntries(
  SUBJECT_ORDER.map((s, i) => [s, i + 1]),
)
export const slotVar = (n: number) => `var(--series-${n})`
export const subjectColor = (s: string) => slotVar(SUBJECT_SLOT[s] ?? 1)

/** Status ramp — reserved, never reused as "series 4". */
export const QUALITY_COLOR: Record<string, string> = {
  high: 'var(--st-good)',
  medium: 'var(--st-warn)',
  low: 'var(--st-serious)',
}

const nf = new Intl.NumberFormat()

/* ------------------------------- scaffolding ------------------------------ */

export function Figure({
  title, subtitle, children, note,
}: { title: string; subtitle?: string; children: ReactNode; note?: ReactNode }) {
  return (
    <figure className="figure">
      <figcaption>
        <h3>{title}</h3>
        {subtitle && <p className="muted">{subtitle}</p>}
      </figcaption>
      {children}
      {note && <p className="fig-note muted">{note}</p>}
    </figure>
  )
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="legend">
      {items.map(i => (
        <li key={i.label}>
          <span className="swatch" style={{ background: i.color }} />
          {i.label}
        </li>
      ))}
    </ul>
  )
}

/* ------------------------------- bar (rows) ------------------------------- */

export interface BarRow { label: string; value: number; color?: string; hint?: string }

/**
 * Horizontal bars. Horizontal because the categories are words — subject and
 * district names read straight across instead of being rotated 45°.
 */
export function BarRows({ rows, unit = '' }: { rows: BarRow[]; unit?: string }) {
  const max = Math.max(1, ...rows.map(r => r.value))
  return (
    <div className="barrows">
      {rows.map(r => (
        <div className="barrow" key={r.label} title={r.hint ?? `${r.label}: ${nf.format(r.value)}${unit}`}>
          <span className="barlabel">{r.label}</span>
          <span className="bartrack">
            <span className="barfill"
                  style={{ width: `${(r.value / max) * 100}%`, background: r.color ?? 'var(--series-1)' }} />
          </span>
          <span className="barvalue tabular">{nf.format(r.value)}</span>
        </div>
      ))}
    </div>
  )
}

/* ------------------------------ stacked bars ------------------------------ */

export interface StackSeries { key: string; label: string; color: string }
export interface StackDatum { label: string; parts: Record<string, number> }

/**
 * Stacked columns over time. A 2px surface gap separates segments so adjacent
 * fills never touch — the cheapest way to keep a stack legible for a reader who
 * cannot distinguish the two hues.
 */
export function StackedColumns({
  data, series, height = 190,
}: { data: StackDatum[]; series: StackSeries[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null)
  const totals = data.map(d => series.reduce((a, s) => a + (d.parts[s.key] ?? 0), 0))
  const max = Math.max(1, ...totals)

  return (
    <div className="stackwrap">
      <div className="stack" style={{ height }}>
        {data.map((d, i) => {
          const total = totals[i]
          return (
            <div className="stackcol" key={d.label}
                 onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <span className="stacktotal tabular">{total ? nf.format(total) : ''}</span>
              <div className="stackbar" style={{ height: `${(total / max) * 100}%` }}>
                {series.map(s => {
                  const v = d.parts[s.key] ?? 0
                  if (!v) return null
                  return (
                    <span key={s.key} className="seg"
                          style={{ flexGrow: v, background: s.color }}
                          title={`${d.label} · ${s.label}: ${nf.format(v)}`} />
                  )
                })}
              </div>
              <span className="stacklabel">{d.label}</span>
              {hover === i && total > 0 && (
                <div className="tip" role="status">
                  <b>{d.label}</b>
                  {series.map(s => (d.parts[s.key] ? (
                    <span key={s.key}>
                      <i className="dot" style={{ background: s.color }} />
                      {s.label}<b className="tabular">{nf.format(d.parts[s.key])}</b>
                    </span>
                  ) : null))}
                </div>
              )}
            </div>
          )
        })}
      </div>
      <Legend items={series.map(s => ({ label: s.label, color: s.color }))} />
    </div>
  )
}

/* -------------------------------- meter ---------------------------------- */

/** A single 100% bar — for one composition, where a pie would be worse. */
export function Meter({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = Math.max(1, parts.reduce((a, p) => a + p.value, 0))
  return (
    <div>
      <div className="meter">
        {parts.map(p => p.value ? (
          <span key={p.label} className="seg" style={{ flexGrow: p.value, background: p.color }}
                title={`${p.label}: ${nf.format(p.value)} (${Math.round(100 * p.value / total)}%)`} />
        ) : null)}
      </div>
      <ul className="legend">
        {parts.map(p => (
          <li key={p.label}>
            <span className="swatch" style={{ background: p.color }} />
            {p.label}
            <b className="tabular">{Math.round((100 * p.value) / total)}%</b>
            <span className="muted tabular">({nf.format(p.value)})</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
