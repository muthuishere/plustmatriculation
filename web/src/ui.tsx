import { useEffect, useState, type ReactNode } from 'react'

/* -------------------------------- theme -------------------------------- */

export type Theme = 'light' | 'dark' | 'system'

const prefersDark = () => window.matchMedia('(prefers-color-scheme: dark)').matches

function paint(theme: Theme) {
  const dark = theme === 'dark' || (theme === 'system' && prefersDark())
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('theme') as Theme) || 'system',
  )
  useEffect(() => {
    localStorage.setItem('theme', theme)
    paint(theme)
    // Following the OS live only makes sense while "system" is selected.
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => paint('system')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])
  return { theme, setTheme }
}

const Sun = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
)
const Moon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
)
const Auto = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="2" y="4" width="20" height="14" rx="2" />
    <path d="M8 21h8M12 18v3" />
  </svg>
)

export function ThemeToggle({ theme, setTheme }: ReturnType<typeof useTheme>) {
  const opts: [Theme, string, ReactNode][] = [
    ['light', 'Light', <Sun key="l" />],
    ['system', 'Match my device', <Auto key="s" />],
    ['dark', 'Dark', <Moon key="d" />],
  ]
  return (
    <div className="theme-toggle" role="group" aria-label="Colour theme">
      {opts.map(([value, label, icon]) => (
        <button key={value} type="button" title={label} aria-label={label}
                aria-pressed={theme === value} onClick={() => setTheme(value)}>
          {icon}
        </button>
      ))}
    </div>
  )
}

/* ------------------------------- controls ------------------------------- */

export function Select({
  label, value, onChange, options, allLabel = 'All',
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: (string | number)[]
  allLabel?: string
}) {
  const id = `f-${label.toLowerCase().replace(/\W+/g, '-')}`
  return (
    <span className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={e => onChange(e.target.value)}>
        <option value="">{allLabel}</option>
        {options.map(o => <option key={String(o)} value={String(o)}>{String(o)}</option>)}
      </select>
    </span>
  )
}

export function Search({
  label = 'Search', value, onChange, placeholder,
}: { label?: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <span className="field grow">
      <label htmlFor="f-search">{label}</label>
      <input id="f-search" type="search" value={value} placeholder={placeholder}
             onChange={e => onChange(e.target.value)} />
    </span>
  )
}

/* --------------------------------- bits --------------------------------- */

export const Tag = ({ kind, children }: { kind?: string; children: ReactNode }) => (
  <span className={'tag' + (kind ? ' ' + kind : '')}>{children}</span>
)

export const Empty = ({ children }: { children: ReactNode }) => (
  <div className="empty">{children}</div>
)

/** Options rendered as a label column + text column, so long option text wraps
 *  under itself rather than under the (a)/(b) marker. */
export function Options({
  options, pickable = false,
}: { options: string[]; pickable?: boolean }) {
  const [picked, setPicked] = useState<number | null>(null)
  useEffect(() => setPicked(null), [options])
  if (!options?.length) return null
  const letters = 'abcdefgh'
  return (
    <ul className={'options' + (pickable ? ' pickable' : '')}>
      {options.map((o, i) => (
        <li key={i}
            {...(pickable
              ? {
                  role: 'button',
                  tabIndex: 0,
                  'aria-pressed': picked === i,
                  onClick: () => setPicked(picked === i ? null : i),
                  onKeyDown: (e: React.KeyboardEvent) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      setPicked(picked === i ? null : i)
                    }
                  },
                }
              : {})}>
          <span className="marker">({letters[i]})</span>
          <span>{o}</span>
        </li>
      ))}
    </ul>
  )
}
