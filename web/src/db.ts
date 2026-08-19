/**
 * DuckDB-WASM data layer.
 *
 * The first version of this app fetched a 4.9 MB questions.json and filtered it
 * in JavaScript. That means every visitor downloads and parses every question
 * before seeing anything, and each keystroke walks 8,000 objects.
 *
 * Parquet is columnar and ZSTD-compressed — the same data is 0.9 MB — and
 * DuckDB reads it with HTTP range requests, so a query that touches three
 * columns never fetches the rest. Filtering, grouping and paging all run in
 * WASM against typed columns instead of in JS against strings.
 */
import * as duckdb from '@duckdb/duckdb-wasm'

let dbp: Promise<duckdb.AsyncDuckDB> | null = null

async function boot(): Promise<duckdb.AsyncDuckDB> {
  const bundles = duckdb.getJsDelivrBundles()
  const bundle = await duckdb.selectBundle(bundles)
  // The worker is fetched as a blob so no separate worker file has to be
  // hosted next to the app — this keeps the GitHub Pages deploy a flat folder.
  const workerUrl = URL.createObjectURL(
    new Blob([`importScripts("${bundle.mainWorker!}");`], { type: 'text/javascript' }),
  )
  const worker = new Worker(workerUrl)
  const logger = new duckdb.VoidLogger()
  const db = new duckdb.AsyncDuckDB(logger, worker)
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker)
  URL.revokeObjectURL(workerUrl)

  // Views over the Parquet files. Relative URLs keep the app working from a
  // local `python3 -m http.server` and from GitHub Pages alike.
  const c = await db.connect()
  const base = new URL('data/', location.href).href
  await c.query(`
    CREATE VIEW questions AS SELECT * FROM read_parquet('${base}questions.parquet');
    CREATE VIEW papers    AS SELECT * FROM read_parquet('${base}papers.parquet');
  `)
  await c.close()
  return db
}

export function db(): Promise<duckdb.AsyncDuckDB> {
  if (!dbp) dbp = boot()
  return dbp
}

/** Run SQL and return plain JS objects. */
export async function query<T = Record<string, unknown>>(sql: string): Promise<T[]> {
  const conn = await (await db()).connect()
  try {
    const res = await conn.query(sql)
    // Arrow values need normalising: BigInt counts would break toLocaleString,
    // and list columns arrive as Arrow vectors rather than arrays.
    return res.toArray().map((row: any) => {
      const o = row.toJSON()
      for (const k of Object.keys(o)) {
        const v = o[k]
        if (typeof v === 'bigint') o[k] = Number(v)
        else if (v && typeof v === 'object' && typeof v.toArray === 'function') {
          o[k] = Array.from(v.toArray(), (x: any) => (typeof x === 'bigint' ? Number(x) : x))
        }
      }
      return o as T
    })
  } finally {
    await conn.close()
  }
}

/** Escape a value for inlining into SQL. Only used for our own filter values. */
export const lit = (s: string) => `'${s.replace(/'/g, "''")}'`

/** Build a WHERE clause from {column: value} pairs, skipping empty values. */
export function where(clauses: Record<string, string | number | undefined | ''>): string {
  const parts = Object.entries(clauses)
    .filter(([, v]) => v !== '' && v !== undefined && v !== null)
    .map(([col, v]) => (typeof v === 'number' ? `${col} = ${v}` : `${col} = ${lit(String(v))}`))
  return parts.length ? 'WHERE ' + parts.join(' AND ') : ''
}
