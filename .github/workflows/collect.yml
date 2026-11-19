name: collect-departures

on:
  schedule:
    # Every 15 minutes between 05:00 and 20:45 UTC (about 06:00 to 22:00 Swiss time)
    - cron: "*/15 5-20 * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: collect
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - run: pip install -r requirements.txt

      - name: Collect one snapshot
        run: python collect.py

      - name: Commit new data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data
          git diff --cached --quiet && exit 0
          git commit -m "data: snapshot $(date -u +%Y-%m-%dT%H:%MZ)"
          git pull --rebase
          git push
