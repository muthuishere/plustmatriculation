/** Shapes emitted by scripts/questionbank.py, plus loading helpers. */

export type Confidence = 'high' | 'medium' | 'low'

export interface Question {
  id: string
  paper: string
  exam: string
  subject: string
  year: string | null
  variant: string | null      // district for term exams, month for annual
  part: string | null
  marks: number | null
  number: number
  question: string
  options: string[]
  confidence: Confidence
  is_answer_key: boolean
  pdf: string
}

export interface Paper {
  paper: string
  exam: string
  subject: string
  year: string | null
  variant: string | null
  is_answer_key: boolean
  questions: number
  pdf: string
  source?: string | null
  hosted?: boolean
}

/** Where the public Parquet + PDFs live. Also shown to users so they can query it. */
export const BUCKET =
  'https://publicassets.hel1.your-objectstorage.com/tn-plus2-papers'

export async function loadData(): Promise<{ papers: Paper[]; questions: Question[] }> {
  const [papers, questions] = await Promise.all([
    fetch('data/papers.json').then(r => r.json() as Promise<Paper[]>),
    fetch('data/questions.json').then(r => r.json() as Promise<Question[]>),
  ])
  return { papers, questions }
}

/* ------------------------------ presentation ------------------------------ */

export const EXAM_LABEL: Record<string, string> = {
  annual: 'Board exam',
  quarterly: 'Quarterly',
  'half-yearly': 'Half-yearly',
}

/** "1 mark" not "1 marks" — small, but it is the sort of thing people notice. */
export const marksLabel = (m: number | null) =>
  m == null ? null : `${m} mark${m === 1 ? '' : 's'}`

export const titleCase = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

export function tagsFor(r: Question | Paper): string[] {
  return [
    titleCase(r.subject),
    EXAM_LABEL[r.exam] ?? r.exam,
    r.year ?? undefined,
    r.variant ? titleCase(r.variant) : undefined,
    'marks' in r ? marksLabel(r.marks) ?? undefined : undefined,
  ].filter(Boolean) as string[]
}

/** docs-relative path to the extracted English text for a paper. */
export const textPath = (pdf: string) =>
  'assets/markdown-english/' +
  pdf.replace(/^.*?(annual|quarterly|half-yearly)\//, '$1/').replace(/\.pdf$/, '.md')

export const uniq = <T,>(xs: T[]): T[] =>
  [...new Set(xs.filter(x => x !== null && x !== undefined && x !== ''))]

export const nf = new Intl.NumberFormat()
