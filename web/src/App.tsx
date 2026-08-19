import { useEffect, useMemo, useState } from 'react'
import {
  BarRows, Figure, Meter, QUALITY_COLOR, StackedColumns, SUBJECT_ORDER, subjectColor,
} from './charts'
import { lit, where } from './db'
import { useDebounced, useQuery, useScalar } from './hooks'
import { BUCKET, EXAM_LABEL, marksLabel, nf, textPath, titleCase } from './data'
import { Empty, Options, Search, Select, Tag, ThemeToggle, useTheme } from './ui'

type Tab = 'overview' | 'papers' | 'questions' | 'practice' | 'data'
const TABS: [Tab, string][] = [
  ['overview', 'Overview'],
  ['papers', 'Papers'],
  ['questions', 'Question bank'],
  ['practice', 'Practice'],
  ['data', 'Open data'],
]

const PAGE = 60

export default function App() {
  const theme = useTheme()
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <>
      <header className="masthead">
        <div className="wrap masthead-in">
          <div className="brand">
            <span className="mark">+2</span>
            <span className="name">TN Question Papers</span>
          </div>
          <span className="spacer" />
          <nav className="tabs" role="tablist">
            {TABS.map(([id, label]) => (
              <button key={id} className="tab" role="tab" aria-selected={tab === id}
                      onClick={() => setTab(id)}>{label}</button>
            ))}
          </nav>
          <ThemeToggle {...theme} />
        </div>
      </header>

      <main className="wrap">
        {tab === 'overview' && <Overview />}
        {tab === 'papers' && <Papers />}
        {tab === 'questions' && <Questions />}
        {tab === 'practice' && <Practice />}
        {tab === 'data' && <OpenData />}
      </main>

      <footer className="wrap">
        Papers set by the Directorate of Government Examinations, Tamil Nadu.
        Collected for study — every paper links back to its source.
      </footer>
    </>
  )
}

/* ------------------------------ shared bits ------------------------------ */

function Loading({ what = 'data' }: { what?: string }) {
  return <div className="empty"><span className="spinner" />Reading the {what}…</div>
}

function Failed({ error }: { error: string }) {
  return (
    <Empty>
      Could not read the dataset.<br />
      <code>{error}</code><br /><br />
      Build it with <code>python3 scripts/questionbank.py &amp;&amp; ./publish dataset</code>.
    </Empty>
  )
}

/** Distinct values for a filter, straight from the column. */
function useDistinct(view: string, col: string, order = col) {
  const { rows } = useQuery<{ v: string | number }>(
    `SELECT DISTINCT ${col} AS v FROM ${view} WHERE ${col} IS NOT NULL ORDER BY ${order}`)
  return rows.map(r => r.v)
}

const Tags = ({ r }: { r: any }) => (
  <div className="tagrow">
    <Tag>{titleCase(r.subject)}</Tag>
    <Tag>{EXAM_LABEL[r.exam] ?? r.exam}</Tag>
    {r.year != null && <Tag>{r.year}</Tag>}
    {r.district && <Tag>{titleCase(r.district)}</Tag>}
    {r.marks != null && <Tag>{marksLabel(r.marks)}</Tag>}
  </div>
)

/* ================================ overview =============================== */

function Overview() {
  const { row: totals, loading, error } = useScalar<any>(`
    SELECT
      (SELECT count(*) FROM papers)                                 AS papers,
      (SELECT count(*) FROM papers WHERE NOT is_answer_key)         AS question_papers,
      (SELECT count(*) FROM papers WHERE is_answer_key)             AS answer_keys,
      (SELECT count(*) FROM questions)                              AS questions,
      (SELECT count(*) FROM questions WHERE confidence='high')      AS clean,
      (SELECT count(*) FROM questions WHERE n_options >= 3)         AS with_options,
      (SELECT count(DISTINCT district) FROM papers WHERE district IS NOT NULL) AS districts`)

  const byYear = useQuery<{ year: number; exam: string; n: number }>(`
    SELECT year, exam, count(*) AS n FROM papers
    WHERE year IS NOT NULL GROUP BY 1,2 ORDER BY 1`)

  const bySubject = useQuery<{ subject: string; n: number }>(`
    SELECT subject, count(*) AS n FROM questions GROUP BY 1 ORDER BY 2 DESC`)

  const byQuality = useQuery<{ confidence: string; n: number }>(`
    SELECT confidence, count(*) AS n FROM questions GROUP BY 1`)

  const topDistricts = useQuery<{ district: string; n: number }>(`
    SELECT district, count(*) AS n FROM papers
    WHERE district IS NOT NULL AND district NOT IN ('model','set')
    GROUP BY 1 ORDER BY 2 DESC LIMIT 10`)

  if (error) return <Failed error={error} />
  if (loading || !totals) return <><Hero /><Loading /></>

  const years = [...new Set(byYear.rows.map(r => r.year))].sort()
  const examKeys = [...new Set(byYear.rows.map(r => r.exam))]
  const stackSeries = examKeys.map((k, i) => ({
    key: k, label: EXAM_LABEL[k] ?? k, color: `var(--series-${i + 1})`,
  }))
  const stackData = years.map(y => ({
    label: String(y),
    parts: Object.fromEntries(byYear.rows.filter(r => r.year === y).map(r => [r.exam, r.n])),
  }))

  const q = Object.fromEntries(byQuality.rows.map(r => [r.confidence, r.n]))

  return (
    <>
      <Hero />
      <div className="statgrid">
        {[
          [nf.format(totals.question_papers), 'question papers'],
          [nf.format(totals.answer_keys), 'answer keys'],
          [nf.format(totals.questions), 'questions extracted'],
          [nf.format(totals.districts), 'districts covered'],
        ].map(([n, l]) => (
          <div className="stat" key={l}>
            <div className="n tabular">{n}</div>
            <div className="l">{l}</div>
          </div>
        ))}
      </div>

      <div className="chartgrid" style={{ marginTop: 10 }}>
        <Figure title="Papers by year"
                subtitle="The board sets one paper statewide; districts each set their own for the term exams."
                note="2021 is empty because no term exams were held that COVID year — absent by fact, not by omission.">
          <StackedColumns data={stackData} series={stackSeries} />
        </Figure>

        <Figure title="Questions by subject"
                subtitle="Extracted from every paper, before any quality filter.">
          <BarRows rows={SUBJECT_ORDER
            .map(s => ({ label: titleCase(s), value: bySubject.rows.find(r => r.subject === s)?.n ?? 0, color: subjectColor(s) }))
            .filter(r => r.value > 0)} />
        </Figure>
      </div>

      <div className="chartgrid" style={{ marginTop: 10 }}>
        <Figure title="How clean is the extracted text?"
                subtitle="Every question is labelled rather than quietly dropped."
                note="Two-column bilingual printing plus OCR on photocopied district papers is what pushes questions into the lower bands. Practice mode uses the clean ones only.">
          <Meter parts={[
            { label: 'Clean', value: q.high ?? 0, color: QUALITY_COLOR.high },
            { label: 'Readable', value: q.medium ?? 0, color: QUALITY_COLOR.medium },
            { label: 'Garbled by the scan', value: q.low ?? 0, color: QUALITY_COLOR.low },
          ]} />
        </Figure>

        <Figure title="Districts with the most papers"
                subtitle="Term exams are set per district, so coverage is uneven.">
          <BarRows rows={topDistricts.rows.map(r => ({
            label: titleCase(r.district), value: r.n, color: 'var(--series-1)',
          }))} />
        </Figure>
      </div>
    </>
  )
}

function Hero() {
  return (
    <section className="hero">
      <h1>Every TN +2 science paper, in one place</h1>
      <p>
        Board, quarterly and half-yearly papers for Physics, Chemistry, Maths, Biology, Botany and
        Zoology — searchable, practisable, and published as open data anyone can query.
      </p>
    </section>
  )
}

/* ================================= papers ================================ */

function Papers() {
  const [exam, setExam] = useState('')
  const [subject, setSubject] = useState('')
  const [year, setYear] = useState('')
  const [text, setText] = useState('')
  const [limit, setLimit] = useState(PAGE)
  const q = useDebounced(text)

  const filters = where({ exam, subject, year: year ? Number(year) : '' })
  const search = q.trim()
    ? `${filters ? 'AND' : 'WHERE'} (paper ILIKE ${lit('%' + q.trim() + '%')})`
    : ''
  const clause = `${filters} ${search}`

  useEffect(() => setLimit(PAGE), [exam, subject, year, q])

  const { row: agg } = useScalar<{ n: number }>(`SELECT count(*) AS n FROM papers ${clause}`)
  const { rows, loading, error } = useQuery<any>(
    `SELECT * FROM papers ${clause} ORDER BY exam, subject, year DESC, district LIMIT ${limit}`)

  const exams = useDistinct('papers', 'exam')
  const subjects = useDistinct('papers', 'subject')
  const years = useDistinct('papers', 'year', 'year DESC')

  if (error) return <Failed error={error} />

  return (
    <>
      <section className="hero">
        <h1>Browse the papers</h1>
        <p>Open the original PDF, or the extracted English text, or the page it was published on.</p>
      </section>

      <div className="toolbar">
        <Select label="Exam" value={exam} onChange={setExam} options={exams as string[]} />
        <Select label="Subject" value={subject} onChange={setSubject} options={subjects as string[]} />
        <Select label="Year" value={year} onChange={setYear} options={years as number[]} />
        <Search value={text} onChange={setText} placeholder="district or paper name…" />
      </div>

      <p className="result-count">
        <b>{nf.format(agg?.n ?? 0)}</b> papers{loading && <> · <span className="spinner" /></>}
      </p>

      {!loading && rows.length === 0 && <Empty>No papers match those filters.</Empty>}
      {rows.map(p => (
        <article className="card" key={p.paper}>
          <h3 className="card-title">
            {titleCase(p.subject)} — {EXAM_LABEL[p.exam] ?? p.exam} {p.year}
            {p.district && p.district !== 'set' ? `, ${titleCase(p.district)}` : ''}
          </h3>
          <Tags r={p} />
          {p.is_answer_key ? <div className="tagrow"><Tag kind="warn">Answer key</Tag></div> : null}
          <div className="linkrow">
            <a href={p.pdf} target="_blank" rel="noopener">Open the PDF</a>
            <a href={textPath(p.pdf)}>Extracted text</a>
            {p.source && <a href={p.source} target="_blank" rel="noopener">Original source</a>}
          </div>
        </article>
      ))}
      {rows.length < (agg?.n ?? 0) && (
        <button className="btn" style={{ marginTop: 12 }} onClick={() => setLimit(l => l + PAGE * 2)}>
          Show more ({nf.format((agg?.n ?? 0) - rows.length)} left)
        </button>
      )}
    </>
  )
}

/* ============================== question bank ============================ */

const CONF_KIND: Record<string, string> = { high: 'good', medium: 'warn', low: 'bad' }
const CONF_LABEL: Record<string, string> = {
  high: 'Clean — text and options intact',
  medium: 'Readable — options may be missing',
  low: 'Garbled by the scan — check the PDF',
}

function Questions() {
  const [subject, setSubject] = useState('')
  const [marks, setMarks] = useState('')
  const [conf, setConf] = useState('high')
  const [text, setText] = useState('')
  const [limit, setLimit] = useState(PAGE)
  const q = useDebounced(text)

  const filters = where({ subject, marks: marks ? Number(marks) : '', confidence: conf })
  const search = q.trim()
    ? `${filters ? 'AND' : 'WHERE'} question ILIKE ${lit('%' + q.trim() + '%')}` : ''
  const clause = `${filters} ${search}`

  useEffect(() => setLimit(PAGE), [subject, marks, conf, q])

  const { row: agg } = useScalar<{ n: number }>(`SELECT count(*) AS n FROM questions ${clause}`)
  const { rows, loading, error } = useQuery<any>(
    `SELECT * FROM questions ${clause} ORDER BY subject, year DESC, number LIMIT ${limit}`)

  const subjects = useDistinct('questions', 'subject')
  const markOpts = useDistinct('questions', 'marks')

  if (error) return <Failed error={error} />

  return (
    <>
      <section className="hero">
        <h1>Search every question</h1>
        <p>
          Filtering runs inside your browser over a compressed columnar file, so searching thousands
          of questions costs one small download and no server at all.
        </p>
      </section>

      <div className="toolbar">
        <Select label="Subject" value={subject} onChange={setSubject} options={subjects as string[]} />
        <Select label="Marks" value={marks} onChange={setMarks} options={markOpts as number[]} />
        <Select label="Quality" value={conf} onChange={setConf} options={['high', 'medium', 'low']} />
        <Search value={text} onChange={setText} placeholder="photosynthesis, matrix, alkane…" />
      </div>

      <p className="result-count">
        <b>{nf.format(agg?.n ?? 0)}</b> questions{conf && <> · {CONF_LABEL[conf]}</>}
        {loading && <> · <span className="spinner" /></>}
      </p>

      {!loading && rows.length === 0 && <Empty>Nothing matches. Try a broader filter.</Empty>}
      {rows.map((r: any, i: number) => (
        <article className="card" key={r.id + '-' + i}>
          <h3 className="card-title serif">{r.question}</h3>
          <Options options={r.options ?? []} />
          <Tags r={r} />
          <div className="tagrow"><Tag kind={CONF_KIND[r.confidence]}>{r.confidence}</Tag></div>
        </article>
      ))}
      {rows.length < (agg?.n ?? 0) && (
        <button className="btn" style={{ marginTop: 12 }} onClick={() => setLimit(l => l + PAGE * 2)}>
          Show more ({nf.format((agg?.n ?? 0) - rows.length)} left)
        </button>
      )}
    </>
  )
}

/* ================================ practice =============================== */

function Practice() {
  const [subject, setSubject] = useState('')
  const [exam, setExam] = useState('')
  const [marks, setMarks] = useState('')
  const [seen, setSeen] = useState(0)
  const [nonce, setNonce] = useState(0)

  const clause = where({ subject, exam, marks: marks ? Number(marks) : '', confidence: 'high' })
  const { row: agg } = useScalar<{ n: number }>(`SELECT count(*) AS n FROM questions ${clause}`)
  // Random draw in SQL, so the pool never has to reach the client. Ordering by
  // a hash of the id plus a nonce is deterministic per draw and, unlike
  // USING SAMPLE, is applied after the WHERE clause rather than before it.
  const { rows, loading, error } = useQuery<any>(
    `SELECT * FROM questions ${clause} ORDER BY hash(id || ${nonce}) LIMIT 1`)

  const subjects = useDistinct('questions', 'subject')
  const exams = useDistinct('questions', 'exam')
  const markOpts = useDistinct('questions', 'marks')
  const current = rows[0]

  const draw = () => { setNonce(n => n + 1); setSeen(s => s + 1) }
  useEffect(() => { setSeen(0) }, [subject, exam, marks])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (/^(INPUT|SELECT|TEXTAREA)$/.test(t?.tagName)) return
      if (e.key === 'n' || e.key === 'N' || e.key === 'ArrowRight') draw()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (error) return <Failed error={error} />

  return (
    <>
      <section className="hero">
        <h1>Practise, one question at a time</h1>
        <p>
          Drawn only from questions that came out of the scan cleanly, so you are never left
          wondering whether a garbled line is your misunderstanding or the scanner's.
        </p>
      </section>

      <div className="toolbar">
        <Select label="Subject" value={subject} onChange={setSubject} options={subjects as string[]} />
        <Select label="Exam" value={exam} onChange={setExam} options={exams as string[]} />
        <Select label="Marks" value={marks} onChange={setMarks} options={markOpts as number[]} />
      </div>

      <div className="card practice">
        {loading && !current && <Loading what="question" />}
        {!loading && !current && (
          <Empty>No clean questions match that combination. Widen the filters — Chemistry and Physics have the most.</Empty>
        )}
        {current && (
          <>
            <div className="practice-head">
              <span className="muted" style={{ fontSize: '.84rem' }}>
                {[titleCase(current.subject), EXAM_LABEL[current.exam] ?? current.exam,
                  current.year, current.district && titleCase(current.district),
                  marksLabel(current.marks)].filter(Boolean).join(' · ')}
              </span>
              <Tag kind="good">Clean extraction</Tag>
            </div>
            <p className="question">{current.question}</p>
            <Options options={current.options ?? []} pickable />
            <div className="actions">
              <button className="btn primary" onClick={draw}>
                Next question <span className="kbd">N</span>
              </button>
              <a className="btn" href={current.pdf} target="_blank" rel="noopener">
                Check the original paper
              </a>
              <span className="spacer" />
              <span className="muted tabular" style={{ fontSize: '.85rem' }}>
                {seen} seen · {nf.format(agg?.n ?? 0)} in this set
              </span>
            </div>
          </>
        )}
      </div>
    </>
  )
}

/* ================================ open data ============================== */

const SAMPLES: { title: string; sql: string }[] = [
  {
    title: 'Which subject has the most clean questions?',
    sql: `SELECT subject, count(*) AS clean_questions
FROM questions WHERE confidence = 'high'
GROUP BY 1 ORDER BY 2 DESC`,
  },
  {
    title: 'How many papers per district and year?',
    sql: `SELECT district, year, count(*) AS papers
FROM papers WHERE district IS NOT NULL
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20`,
  },
  {
    title: 'Which words show up most in Physics questions?',
    sql: `SELECT lower(w) AS word, count(*) AS n
FROM questions, unnest(string_split(question, ' ')) AS t(w)
WHERE subject = 'physics' AND length(w) > 6
GROUP BY 1 ORDER BY 2 DESC LIMIT 15`,
  },
]

function OpenData() {
  const [sql, setSql] = useState(SAMPLES[0].sql)
  const [run, setRun] = useState(SAMPLES[0].sql)
  const { rows, loading, error } = useQuery<any>(run)
  const cols = rows.length ? Object.keys(rows[0]) : []

  const remote = `${BUCKET}/data/questions.parquet`

  return (
    <>
      <section className="hero">
        <h1>Open data, not a walled garden</h1>
        <p>
          The whole dataset is public Parquet on object storage. No sign-up, no API key, no
          download — and the query box below runs DuckDB inside your own browser.
        </p>
      </section>

      <div className="callout" style={{ marginBottom: 10 }}>
        <h3>Use it from anywhere</h3>
        <pre className="sql">{`duckdb -c "SELECT subject, count(*) FROM '${remote}' GROUP BY 1"`}</pre>
        <p style={{ marginTop: 10 }}>
          Also available: <code>papers.parquet</code> and <code>coverage.parquet</code>, plus every
          source PDF, in the same bucket.
        </p>
      </div>

      <div className="figure">
        <figcaption style={{ marginBottom: 12 }}>
          <h3>Try a query</h3>
          <p className="muted">Runs locally against <code>questions</code> and <code>papers</code>.</p>
        </figcaption>
        <div className="tagrow" style={{ marginBottom: 10 }}>
          {SAMPLES.map(s => (
            <button key={s.title} className="tag" style={{ cursor: 'pointer' }}
                    onClick={() => { setSql(s.sql); setRun(s.sql) }}>{s.title}</button>
          ))}
        </div>
        <textarea className="sqlbox" value={sql} spellCheck={false} rows={5}
                  onChange={e => setSql(e.target.value)} />
        <div className="actions" style={{ marginTop: 12, paddingTop: 0, borderTop: 0 }}>
          <button className="btn primary" onClick={() => setRun(sql)}>Run query</button>
          {loading && <span className="muted"><span className="spinner" />running…</span>}
        </div>

        {error && <p className="fig-note" style={{ color: 'var(--st-serious)' }}>{error}</p>}
        {!error && rows.length > 0 && (
          <div className="tablewrap" style={{ marginTop: 14 }}>
            <table>
              <thead><tr>{cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>
                {rows.slice(0, 50).map((r, i) => (
                  <tr key={i}>{cols.map(c => (
                    <td key={c} className={typeof r[c] === 'number' ? 'num' : ''}>
                      {r[c] == null ? '—' : String(r[c])}
                    </td>
                  ))}</tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!error && !loading && rows.length > 50 && (
          <p className="fig-note">Showing the first 50 of {nf.format(rows.length)} rows.</p>
        )}
      </div>
    </>
  )
}
