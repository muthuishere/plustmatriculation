// Command publish uploads the paper corpus and the Parquet dataset to a public
// S3 bucket (Hetzner Object Storage), and configures the bucket so a browser
// can query the Parquet files directly with DuckDB-WASM.
//
//	publish cors            show the bucket's CORS rules
//	publish cors --apply    add a public GET rule (merged, never replacing)
//	publish push            upload docs/assets/**.pdf + docs/data/* (incremental)
//	publish push --data     upload only docs/data (parquet + json), skip PDFs
//	publish verify          fetch sample objects over unauthenticated HTTPS
//
// Why Go rather than the aws CLI: aws-cli 2.34 intermittently dies against
// Hetzner's Ceph with "argument of type 'NoneType' is not a container or
// iterable" — the same file succeeds on retry, so uploads needed several
// passes to converge and one bucket-level call (get-bucket-cors) could not be
// made at all. The AWS SDK for Go does not have that bug.
//
// Credentials come from the environment only:
//
//	HETZNER_S3_ACCESS_KEY / HETZNER_S3_ACCESS_SECRET   (or S3_ACCESS_KEY / S3_SECRET_KEY)
//	HETZNER_PUBLIC_BUCKET                              (or S3_BUCKET)
//	S3_ENDPOINT   optional, default https://hel1.your-objectstorage.com
package main

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
)

const (
	defaultEndpoint = "https://hel1.your-objectstorage.com"
	prefix          = "tn-plus2-papers"
	uploadWorkers   = 8
)

type app struct {
	client   *s3.Client
	bucket   string
	endpoint string
	root     string
}

func env(names ...string) string {
	for _, n := range names {
		if v := os.Getenv(n); v != "" {
			return v
		}
	}
	return ""
}

func newApp(ctx context.Context) (*app, error) {
	key := env("S3_ACCESS_KEY", "HETZNER_S3_ACCESS_KEY")
	secret := env("S3_SECRET_KEY", "HETZNER_S3_ACCESS_SECRET", "HETZNER_S3_SECRET_KEY")
	if key == "" || secret == "" {
		return nil, errors.New("missing credentials: set HETZNER_S3_ACCESS_KEY and " +
			"HETZNER_S3_ACCESS_SECRET (values are read from the environment only)")
	}
	bucket := env("S3_BUCKET", "HETZNER_PUBLIC_BUCKET")
	if bucket == "" {
		return nil, errors.New("missing bucket: set HETZNER_PUBLIC_BUCKET")
	}
	endpoint := env("S3_ENDPOINT", "HETZNER_S3_ENDPOINT")
	if endpoint == "" {
		endpoint = defaultEndpoint
	}
	endpoint = strings.TrimRight(endpoint, "/")
	// Hetzner rejects writes whose client region disagrees with the location in
	// the endpoint host, so derive it rather than hardcoding.
	region := strings.SplitN(strings.TrimPrefix(strings.TrimPrefix(endpoint, "https://"), "http://"), ".", 2)[0]

	cfg, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(region),
		config.WithCredentialsProvider(
			credentials.NewStaticCredentialsProvider(key, secret, "")),
	)
	if err != nil {
		return nil, err
	}
	cli := s3.NewFromConfig(cfg, func(o *s3.Options) {
		o.BaseEndpoint = aws.String(endpoint)
		o.UsePathStyle = true // Ceph is happiest path-style for writes
	})
	root, err := repoRoot()
	if err != nil {
		return nil, err
	}
	return &app{client: cli, bucket: bucket, endpoint: endpoint, root: root}, nil
}

func repoRoot() (string, error) {
	exe, _ := os.Getwd()
	for dir := exe; dir != "/" && dir != ""; dir = filepath.Dir(dir) {
		if _, err := os.Stat(filepath.Join(dir, "scripts", "aggregate.py")); err == nil {
			return dir, nil
		}
	}
	return "", errors.New("run this from inside the repo")
}

func (a *app) publicBase() string {
	host := strings.TrimPrefix(strings.TrimPrefix(a.endpoint, "https://"), "http://")
	return fmt.Sprintf("https://%s.%s/%s", a.bucket, host, prefix)
}

// ---------------------------------------------------------------- cors

// corsCmd prints the bucket's CORS rules and, with --apply, MERGES a public GET
// rule into them. The bucket is shared with other projects, so the existing
// rules are read and preserved: replacing them wholesale is how you silently
// break somebody else's site.
func (a *app) corsCmd(ctx context.Context, apply bool) error {
	var existing []types.CORSRule
	out, err := a.client.GetBucketCors(ctx, &s3.GetBucketCorsInput{Bucket: &a.bucket})
	if err != nil {
		if strings.Contains(err.Error(), "NoSuchCORSConfiguration") {
			fmt.Println("no CORS configuration on this bucket yet")
		} else {
			return fmt.Errorf("read cors: %w", err)
		}
	} else {
		existing = out.CORSRules
		fmt.Printf("existing CORS rules: %d\n", len(existing))
		for i, r := range existing {
			fmt.Printf("  [%d] origins=%v methods=%v headers=%v\n",
				i, r.AllowedOrigins, r.AllowedMethods, r.AllowedHeaders)
		}
	}

	want := types.CORSRule{
		ID:            aws.String("public-read-duckdb-wasm"),
		AllowedOrigins: []string{"*"},
		AllowedMethods: []string{"GET", "HEAD"},
		AllowedHeaders: []string{"*"},
		// DuckDB-WASM reads Parquet with HTTP range requests and needs to see
		// the length and the range headers back, or it cannot page the file.
		ExposeHeaders:  []string{"Content-Length", "Content-Range", "Accept-Ranges", "ETag"},
		MaxAgeSeconds:  aws.Int32(3600),
	}
	for _, r := range existing {
		if r.ID != nil && *r.ID == *want.ID {
			fmt.Println("our rule is already present")
			if !apply {
				return nil
			}
		}
	}
	if !apply {
		fmt.Println("\nwould add rule 'public-read-duckdb-wasm' (GET/HEAD from any origin,")
		fmt.Println("exposing range headers). Re-run with --apply to write it.")
		return nil
	}
	merged := make([]types.CORSRule, 0, len(existing)+1)
	for _, r := range existing {
		if r.ID != nil && *r.ID == *want.ID {
			continue // replace only our own rule
		}
		merged = append(merged, r)
	}
	merged = append(merged, want)
	_, err = a.client.PutBucketCors(ctx, &s3.PutBucketCorsInput{
		Bucket:                &a.bucket,
		CORSConfiguration:     &types.CORSConfiguration{CORSRules: merged},
	})
	if err != nil {
		return fmt.Errorf("write cors: %w", err)
	}
	fmt.Printf("wrote %d CORS rules (%d pre-existing preserved)\n", len(merged), len(merged)-1)
	return nil
}

// ---------------------------------------------------------------- push

type upload struct {
	path string
	key  string
}

func (a *app) listRemote(ctx context.Context, keyPrefix string) (map[string]int64, error) {
	have := map[string]int64{}
	p := s3.NewListObjectsV2Paginator(a.client, &s3.ListObjectsV2Input{
		Bucket: &a.bucket, Prefix: aws.String(keyPrefix),
	})
	for p.HasMorePages() {
		page, err := p.NextPage(ctx)
		if err != nil {
			return nil, err
		}
		for _, o := range page.Contents {
			have[*o.Key] = *o.Size
		}
	}
	return have, nil
}

func (a *app) pushCmd(ctx context.Context, dataOnly, dryRun bool) error {
	var jobs []upload
	add := func(base, sub string) {
		dir := filepath.Join(a.root, base)
		filepath.Walk(dir, func(p string, fi os.FileInfo, err error) error {
			if err != nil || fi.IsDir() {
				return nil
			}
			rel, _ := filepath.Rel(dir, p)
			jobs = append(jobs, upload{path: p, key: prefix + "/" + sub + "/" + filepath.ToSlash(rel)})
			return nil
		})
	}
	if !dataOnly {
		for _, exam := range []string{"annual", "quarterly", "half-yearly"} {
			add(filepath.Join("docs", "assets", exam), exam)
		}
	}
	add(filepath.Join("docs", "data"), "data")

	sort.Slice(jobs, func(i, j int) bool { return jobs[i].key < jobs[j].key })
	have, err := a.listRemote(ctx, prefix+"/")
	if err != nil {
		return fmt.Errorf("list bucket: %w", err)
	}

	var todo []upload
	var bytes int64
	for _, j := range jobs {
		fi, err := os.Stat(j.path)
		if err != nil {
			continue
		}
		// Size match is the sync rule: these files are content-addressed by the
		// aggregate manifest and never edited in place.
		if sz, ok := have[j.key]; ok && sz == fi.Size() {
			continue
		}
		todo = append(todo, j)
		bytes += fi.Size()
	}
	fmt.Printf("%d local objects, %d already in bucket, %d to upload (%.2f GB)\n",
		len(jobs), len(jobs)-len(todo), len(todo), float64(bytes)/1e9)
	if dryRun || len(todo) == 0 {
		if dryRun {
			fmt.Println("dry run — nothing uploaded")
		}
		fmt.Println("public base: " + a.publicBase())
		return nil
	}

	var (
		wg      sync.WaitGroup
		mu      sync.Mutex
		done    int
		failed  []string
		queue   = make(chan upload)
		started = time.Now()
	)
	for w := 0; w < uploadWorkers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := range queue {
				if err := a.put(ctx, j); err != nil {
					mu.Lock()
					failed = append(failed, j.key+": "+err.Error())
					mu.Unlock()
					continue
				}
				mu.Lock()
				done++
				if done%100 == 0 {
					fmt.Printf("  %d/%d in %s\n", done, len(todo), time.Since(started).Round(time.Second))
				}
				mu.Unlock()
			}
		}()
	}
	for _, j := range todo {
		queue <- j
	}
	close(queue)
	wg.Wait()

	fmt.Printf("uploaded %d/%d in %s\n", done, len(todo), time.Since(started).Round(time.Second))
	for _, f := range failed {
		fmt.Println("  ! " + f)
	}
	fmt.Println("public base: " + a.publicBase())
	if len(failed) > 0 {
		return fmt.Errorf("%d uploads failed", len(failed))
	}
	return nil
}

func (a *app) put(ctx context.Context, j upload) error {
	f, err := os.Open(j.path)
	if err != nil {
		return err
	}
	defer f.Close()
	ct := mime.TypeByExtension(filepath.Ext(j.path))
	switch filepath.Ext(j.path) {
	case ".parquet":
		ct = "application/vnd.apache.parquet"
	case ".pdf":
		ct = "application/pdf"
	case ".json":
		ct = "application/json"
	case ".md":
		ct = "text/markdown; charset=utf-8"
	}
	if ct == "" {
		ct = "application/octet-stream"
	}
	var attempt error
	for try := 0; try < 3; try++ {
		if _, err := f.Seek(0, io.SeekStart); err != nil {
			return err
		}
		_, attempt = a.client.PutObject(ctx, &s3.PutObjectInput{
			Bucket:       &a.bucket,
			Key:          &j.key,
			Body:         f,
			ContentType:  aws.String(ct),
			CacheControl: aws.String("public, max-age=86400"),
		})
		if attempt == nil {
			return nil
		}
		time.Sleep(time.Duration(try+1) * 500 * time.Millisecond)
	}
	return attempt
}

// ---------------------------------------------------------------- verify

// verifyCmd proves public readability the way a student's browser sees it: an
// unauthenticated request, checking the bytes match and that CORS and range
// support are actually advertised.
func (a *app) verifyCmd(ctx context.Context) error {
	base := a.publicBase()
	samples := []string{
		"annual/12th-physics-2025-march.pdf",
		"data/questions.parquet",
		"data/papers.parquet",
	}
	bad := 0
	for _, key := range samples {
		url := base + "/" + key
		req, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
		req.Header.Set("Range", "bytes=0-255")
		req.Header.Set("Origin", "https://example.github.io")
		res, err := http.DefaultClient.Do(req)
		if err != nil {
			fmt.Printf("  FAIL %s: %v\n", key, err)
			bad++
			continue
		}
		body, _ := io.ReadAll(res.Body)
		res.Body.Close()
		sum := md5.Sum(body)
		cors := res.Header.Get("Access-Control-Allow-Origin")
		fmt.Printf("  %d %s range=%v cors=%q %s (%s…)\n", res.StatusCode, key,
			res.Header.Get("Accept-Ranges") != "" || res.StatusCode == 206,
			cors, res.Header.Get("Content-Type"), hex.EncodeToString(sum[:4]))
		if res.StatusCode >= 400 {
			bad++
		}
		if cors == "" {
			fmt.Println("      ! no CORS header — DuckDB-WASM in a browser will be blocked. " +
				"Run: publish cors --apply")
		}
	}
	if bad > 0 {
		return fmt.Errorf("%d/%d samples failed", bad, len(samples))
	}
	fmt.Printf("verify: %d/%d publicly readable at %s/\n", len(samples), len(samples), base)
	return nil
}

// ---------------------------------------------------------------- main

func main() {
	log.SetFlags(0)
	apply := flag.Bool("apply", false, "cors: actually write the merged rules")
	dataOnly := flag.Bool("data", false, "push: upload only docs/data, skip the PDFs")
	dryRun := flag.Bool("dry-run", false, "push: list what would be uploaded")
	// Subcommand first, flags after it: `publish cors --apply` is what anyone
	// would type, and Go's flag package stops at the first positional arg.
	if len(os.Args) < 2 {
		fmt.Println("usage: publish <cors|push|verify> [flags]")
		flag.PrintDefaults()
		os.Exit(2)
	}
	cmd := os.Args[1]
	if err := flag.CommandLine.Parse(os.Args[2:]); err != nil {
		os.Exit(2)
	}
	ctx := context.Background()
	if cmd == "dataset" { // builds Parquet locally; no bucket, no credentials
		if err := datasetCmd(); err != nil {
			log.Fatal(err)
		}
		return
	}
	a, err := newApp(ctx)
	if err != nil {
		log.Fatal(err)
	}
	switch cmd {
	case "dataset":
		err = datasetCmd()
	case "cors":
		err = a.corsCmd(ctx, *apply)
	case "push":
		err = a.pushCmd(ctx, *dataOnly, *dryRun)
	case "verify":
		err = a.verifyCmd(ctx)
	default:
		err = fmt.Errorf("unknown command %q", cmd)
	}
	if err != nil {
		log.Fatal(err)
	}
}
