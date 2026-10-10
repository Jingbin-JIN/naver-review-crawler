# naver-review-crawler

A small Python tool that collects visitor reviews and basic place information (total review count, number of coupons on offer) from Naver Place — Korea's main local-business platform — for a fixed list of restaurants, and writes them to CSV and Excel. I use it in a 2026 undergraduate team research project on incentivised restaurant reviews (reviews written in exchange for coupons or free items); the project tracks a few dozen restaurants and needs their newest reviews once a day, with a flag on reviews that mention a review event.

Korean usage notes for my team are in [README.ko.md](README.ko.md).

## What it does

- Reads the list of places from the team's spreadsheet (`.xlsx`, one tab per team member) or from Naver Map share links. Places without a link are looked up by name on Naver Map, accepting only an exact name match near the expected district.
- **Default (`http`) engine:** downloads each place's mobile review page and parses the Apollo GraphQL state embedded in the HTML, which carries the place record, the coupon count and the ten most recent visitor reviews. No browser needed.
- **Browser engine (`--engine browser`):** opens the page with Playwright and clicks "more" to collect further pages of reviews from the GraphQL responses.
- Normalises each review into fixed columns (written/visited dates, rating, body and length, photo count excluding receipt photos, verification method, visit count, chosen keywords, reviewer's review/photo counts) and flags bodies that mention a review event or a free item.
- Appends to a cumulative `reviews.csv` (deduplicated by review id), writes a per-run Excel file with a *reviews* sheet and a *places* sheet, and keeps a `run_log.csv` so that daily changes in review and coupon counts can be followed.

```
python crawl.py run --input team_sheet.xlsx --sheet <tab>   # collect every place on a tab
python crawl.py run --place "<share link>" [--place ...]     # collect by link only
python crawl.py probe --place "<share link>"                 # dump the page's data structure for one place
python crawl.py export                                       # whole cumulative CSV as one Excel file
```

## Privacy and crawling rules

- Nicknames, profile images and links, user ids and blog-author details are stripped before anything is saved — raw JSON dumps and probe summaries included. A reviewer can only be distinguished across reviews when a secret `REVIEW_SALT` is set, and then only as a 12-character keyed hash.
- Only the tracked places are visited, once a day, with a 4–8 second pause between places. If Naver asks for a CAPTCHA the place is recorded as an error and retried later; the tool never tries to bypass it.
- Naver's terms restrict automated access; this is small-scale collection for a supervised research project, within the scope agreed with the advisor.

## Layout

```
crawl.py                  command-line entry point (run, probe, export)
naver_reviews/web.py      http engine: page download, name search
naver_reviews/browser.py  Playwright engine: open page, click "more", capture responses
naver_reviews/extract.py  find reviews in the captured data, normalise fields, scrub personal data, flag event mentions
naver_reviews/ids.py      place id / name from links and share texts
naver_reviews/places.py   read the team sheet (xlsx) or a CSV
naver_reviews/store.py    cumulative CSV, Excel export
naver_reviews/net.py      minimal HTTP helper (certificate handling on macOS)
tests/                    50 unit and end-to-end tests (fake page data modelled on the real structure; a local fake server for both engines)
setup_mac.sh              one-time setup on macOS: venv, dependencies, Chromium, tests
```

Requires Python 3.9+, `playwright`, `openpyxl`, `certifi`; run `python -m unittest` to check.

## Status and origin

v0.2 (October 2026). Verified against the live site on 9 October 2026 for 29 places (name search 29/29, review fields, place fields, personal-data removal). Whether the browser engine's "more" button works on the live site has not been confirmed.

This tool was written with AI assistance (Claude) under my direction: I set the requirements and the privacy rules, reviewed the code, and tested and run it for the project. The Naver page structure it relies on was last checked in October 2026 and may change.

## License

MIT — see [LICENSE](LICENSE).
