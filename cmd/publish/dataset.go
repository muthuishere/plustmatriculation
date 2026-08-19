package main

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"

	_ "github.com/marcboeker/go-duckdb/v2"
)

// datasetCmd builds the public Parquet dataset with an in-process DuckDB.
//
// The JSON that questionbank.py emits is convenient for the site but useless
// for analysis: 30 MB of repeated strings that a browser must parse in full
// before showing anything. Parquet is columnar and ZSTD-compressed, so
// DuckDB-WASM can range-request only the columns a query touches — the same
// file serves a student's practice screen and someone's ad-hoc SQL.
//
// Anyone can query the published files with no download and no account:
//
//	duckdb -c "SELECT subject, count(*) FROM
//	  'https://publicassets.hel1.your-objectstorage.com/tn-plus2-papers/data/questions.parquet'
//	  GROUP BY 1"
func datasetCmd() error {
	root, err := repoRoot()
	if err != nil {
		return err
	}
	dataDir := filepath.Join(root, "docs", "data")
	for _, f := range []string{"questions.json", "papers.json"} {
		if _, err := os.Stat(filepath.Join(dataDir, f)); err != nil {
			return fmt.Errorf("%s missing — run `python3 scripts/questionbank.py` first", f)
		}
	}

	db, err := sql.Open("duckdb", "")
	if err != nil {
		return err
	}
	defer db.Close()

	var version string
	if err := db.QueryRow("SELECT version()").Scan(&version); err != nil {
		return err
	}
	fmt.Printf("duckdb %s (in-process)\n", version)

	steps := []struct {
		name string
		stmt string
	}{
		{"questions", `
			CREATE OR REPLACE TABLE questions AS
			SELECT
			  id, paper, exam, subject,
			  TRY_CAST(year AS INTEGER)  AS year,
			  variant                    AS district,
			  part,
			  TRY_CAST(marks AS INTEGER) AS marks,
			  TRY_CAST(number AS INTEGER) AS number,
			  question,
			  options,
			  len(options)               AS n_options,
			  confidence,
			  is_answer_key,
			  pdf
			FROM read_json_auto(?, maximum_object_size=100000000)`},
		{"papers", `
			CREATE OR REPLACE TABLE papers AS
			SELECT
			  paper, exam, subject,
			  TRY_CAST(year AS INTEGER) AS year,
			  variant                   AS district,
			  is_answer_key,
			  TRY_CAST(questions AS INTEGER) AS n_questions,
			  pdf, source
			FROM read_json_auto(?, maximum_object_size=100000000)`},
	}
	for _, s := range steps {
		if _, err := db.Exec(s.stmt, filepath.Join(dataDir, s.name+".json")); err != nil {
			return fmt.Errorf("build %s: %w", s.name, err)
		}
		var n int64
		if err := db.QueryRow("SELECT count(*) FROM " + s.name).Scan(&n); err != nil {
			return err
		}
		out := filepath.Join(dataDir, s.name+".parquet")
		// ZSTD over the default SNAPPY: these columns are highly repetitive
		// (subject, exam, district), and the site pays for every byte twice —
		// once in egress, once in the student's data plan.
		_, err := db.Exec(fmt.Sprintf(
			"COPY %s TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 50000)",
			s.name, out))
		if err != nil {
			return fmt.Errorf("write %s: %w", out, err)
		}
		ji, _ := os.Stat(filepath.Join(dataDir, s.name+".json"))
		pi, _ := os.Stat(out)
		fmt.Printf("  %-10s %7d rows  json %6.1f MB -> parquet %5.1f MB (%.0f%% smaller)\n",
			s.name, n, float64(ji.Size())/1e6, float64(pi.Size())/1e6,
			100*(1-float64(pi.Size())/float64(ji.Size())))
	}

	// A tiny summary table so the dashboard's landing view is one small fetch
	// instead of a scan over the full question set.
	if _, err := db.Exec(`
		CREATE OR REPLACE TABLE coverage AS
		SELECT exam, subject, year, district,
		       count(*) FILTER (WHERE NOT is_answer_key) AS papers,
		       count(*) FILTER (WHERE is_answer_key)     AS answer_keys,
		       sum(n_questions)                          AS questions
		FROM papers GROUP BY ALL ORDER BY exam, subject, year`); err != nil {
		return err
	}
	out := filepath.Join(dataDir, "coverage.parquet")
	if _, err := db.Exec(fmt.Sprintf(
		"COPY coverage TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)", out)); err != nil {
		return err
	}
	var rows int64
	db.QueryRow("SELECT count(*) FROM coverage").Scan(&rows)
	fmt.Printf("  %-10s %7d rows\n", "coverage", rows)

	// Show what a consumer would actually get.
	fmt.Println("\nsanity check — questions by subject and confidence:")
	r, err := db.Query(`SELECT subject,
	                      count(*) AS total,
	                      count(*) FILTER (WHERE confidence='high') AS high,
	                      count(*) FILTER (WHERE n_options >= 3)    AS with_options
	                    FROM questions GROUP BY 1 ORDER BY 2 DESC`)
	if err != nil {
		return err
	}
	defer r.Close()
	fmt.Printf("  %-10s %8s %8s %12s\n", "subject", "total", "high", "with options")
	for r.Next() {
		var subj string
		var total, high, opts int64
		if err := r.Scan(&subj, &total, &high, &opts); err != nil {
			return err
		}
		fmt.Printf("  %-10s %8d %8d %12d\n", subj, total, high, opts)
	}
	return r.Err()
}
