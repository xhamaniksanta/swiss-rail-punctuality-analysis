name: build-report

on:
  schedule:
    # Every day at 21:30 UTC, after the last collection run
    - cron: "30 21 * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: collect
  cancel-in-progress: false

jobs:
  report:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - run: pip install -r requirements.txt

      - name: Build report
        run: python report.py

      - name: Commit report
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add reports
          git diff --cached --quiet && exit 0
          git commit -m "report: update results"
          git pull --rebase
          git push
