import { useEffect, useRef, useState } from 'react'
import { query } from './db'

/** Debounce a fast-changing value (search boxes) so we do not re-query per keystroke. */
export function useDebounced<T>(value: T, ms = 180): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

/**
 * Run a SQL query, keeping the previous rows on screen while the next one runs.
 * Without that the list blanks on every filter change, which reads as slower
 * than it is. Out-of-order responses are dropped by sequence number.
 */
export function useQuery<T = Record<string, unknown>>(sql: string | null) {
  const [rows, setRows] = useState<T[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const seq = useRef(0)

  useEffect(() => {
    if (sql == null) return
    const my = ++seq.current
    setLoading(true)
    query<T>(sql)
      .then(r => { if (my === seq.current) { setRows(r); setError(null) } })
      .catch(e => { if (my === seq.current) setError(String(e?.message ?? e)) })
      .finally(() => { if (my === seq.current) setLoading(false) })
  }, [sql])

  return { rows, loading, error }
}

/** Convenience for single-row aggregates. */
export function useScalar<T = Record<string, unknown>>(sql: string | null) {
  const { rows, loading, error } = useQuery<T>(sql)
  return { row: rows[0], loading, error }
}
