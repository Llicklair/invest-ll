# Daily forward test of the pre-registered crypto portfolio.
#
# Downloads the latest closed day for every Binance USDT pair, records the portfolio's targets
# in paper/momentum.jsonl and commits that one file. The commit is the point: a record dated
# before the outcome is known is the only evidence a backtest cannot fake.
#
# It never sends orders and never pushes unless asked.
#
# Usage:  .\scripts\paper-daily.ps1          record and commit locally
#         .\scripts\paper-daily.ps1 -Push    also push the commit
#
# To run it every day at 02:30 (after the 00:00 UTC close), register it once:
#   schtasks /Create /SC DAILY /ST 02:30 /TN "INVEST LL paper" `
#     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File $PWD\scripts\paper-daily.ps1"

param([switch]$Push)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"

uv run invest-ll-quant download
if ($LASTEXITCODE -ne 0) { Write-Host "Download failed; nothing recorded." -ForegroundColor Red; exit 1 }

uv run invest-ll-quant paper record
if ($LASTEXITCODE -ne 0) { Write-Host "Recording failed (already recorded today?)." -ForegroundColor Yellow; exit 1 }

uv run invest-ll-quant paper status

git add paper/momentum.jsonl
git commit -m "paper: record $(Get-Date -Format yyyy-MM-dd)" --quiet
if ($Push) { git push --quiet }
