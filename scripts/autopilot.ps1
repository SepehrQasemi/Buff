[CmdletBinding()]
param(
  [ValidateSet("docs", "tooling", "runtime")]
  [string]$Lane = "docs",
  [string]$Title = "",
  [switch]$Merge
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = (git rev-parse --show-toplevel | Out-String).Trim()
if (-not $root) { throw "NOT_A_GIT_REPO" }
Set-Location $root

function RunGit([string]$label, [string[]]$args) {
  Write-Output ""
  Write-Output ("=== " + $label + " ===")
  Write-Output ("git " + ($args -join " "))
  $out = & git @args 2>&1
  $c = $LASTEXITCODE
  @($out) | ForEach-Object { Write-Output $_ }
  if ($c -ne 0) { throw ("FAIL(" + $label + "):" + $c) }
}

function Run([string]$label, [scriptblock]$sb, [switch]$AllowRgNoMatch) {
  Write-Output ""
  Write-Output ("=== " + $label + " ===")
  $out = & $sb 2>&1
  $c = $LASTEXITCODE
  @($out) | ForEach-Object { Write-Output $_ }
  if ($AllowRgNoMatch) {
    if ($c -gt 1) { throw ("FAIL(" + $label + "):" + $c) }
  } else {
    if ($c -ne 0) { throw ("FAIL(" + $label + "):" + $c) }
  }
}

RunGit "main" @("switch", "main")
RunGit "pull" @("pull", "--ff-only")
Run "ruff format" { python -m ruff format . }
Run "ruff check" { python -m ruff check . }
Run "pytest" { python -m pytest -q }
Run "release_gate" { python -m tools.release_gate --strict --timeout-seconds 900 }

$open = (gh pr list --state open --limit 50 --json number,title,url | Out-String).Trim()
if (-not $open) { throw "GH_PR_LIST_FAILED" }
$openCount = ($open | python -c "import sys,json; print(len(json.load(sys.stdin)))").Trim()
Write-Output ("OPEN_PR_COUNT=" + $openCount)
if ([int]$openCount -ne 0) {
  $open | python -c "import sys,json; d=json.load(sys.stdin); [print('- #{} {} {}'.format(x['number'],x['title'],x['url'])) for x in d]"
  throw "OPEN_PRS_EXIST__STOP"
}

# Lane scope policy (fail if dirty outside lane)
$porc = & git status --porcelain
$paths = @()
foreach ($ln in @($porc)) {
  if ([string]::IsNullOrWhiteSpace($ln)) { continue }
  if ($ln.Length -lt 4) { continue }
  $p = $ln.Substring(3).Trim()
  if ($p -match " -> ") { $p = ($p -split " -> ")[-1].Trim() }
  $p = $p -replace "\\", "/"
  if ($p) { $paths += $p }
}
$paths = @($paths | Sort-Object -Unique)

if ($Lane -eq "docs") {
  $bad = @($paths | Where-Object { ($_ -ne "README.md") -and (-not $_.StartsWith("docs/")) })
  if ($bad.Count -gt 0) {
    Write-Output "SCOPE_OFFENDERS:"
    $bad | ForEach-Object { Write-Output $_ }
    throw "SCOPE_VIOLATION_WORKTREE"
  }
} elseif ($Lane -eq "tooling") {
  $bad = @($paths | Where-Object { -not $_.StartsWith("scripts/") })
  if ($bad.Count -gt 0) {
    Write-Output "SCOPE_OFFENDERS:"
    $bad | ForEach-Object { Write-Output $_ }
    throw "SCOPE_VIOLATION_WORKTREE"
  }
}

# If nothing to do, exit clean
if ($paths.Count -eq 0) {
  Write-Output "NO_CHANGES=PASS"
  exit 0
}

# Create PR branch
$stamp = (Get-Date -Format "yyyyMMdd")
$branch = ("chore/" + $Lane + "-autopilot-" + $stamp)
RunGit "new branch" @("switch", "-c", $branch)

# Stage lane files only
if ($Lane -eq "docs") {
  foreach ($p in @($paths | Where-Object { ($_ -eq "README.md") -or $_.StartsWith("docs/") })) {
    RunGit ("add " + $p) @("add", "--", $p)
  }
} elseif ($Lane -eq "tooling") {
  foreach ($p in @($paths | Where-Object { $_.StartsWith("scripts/") })) {
    RunGit ("add " + $p) @("add", "--", $p)
  }
}

$staged = @((& git diff --cached --name-only) | ForEach-Object { ($_ | Out-String).Trim() -replace "\\", "/" } | Where-Object { $_ })
if ($Lane -eq "docs") {
  $bad = @($staged | Where-Object { ($_ -ne "README.md") -and (-not $_.StartsWith("docs/")) })
  if ($bad.Count -gt 0) {
    Write-Output "BAD_STAGED:"
    $bad | ForEach-Object { Write-Output $_ }
    throw "SCOPE_VIOLATION_STAGED"
  }
}

if ($staged.Count -eq 0) {
  Write-Output "NO_STAGED=STOP"
  exit 0
}

if (-not $Title) { $Title = ("chore(" + $Lane + "): autopilot update") }
RunGit "commit" @("commit", "-m", $Title)
RunGit "push" @("push", "-u", "origin", $branch)

$body = @(
  "## Summary",
  "- autopilot update via scripts/autopilot.ps1",
  "",
  "## Validation",
  "- python -m tools.release_gate --strict --timeout-seconds 900"
) -join "`n"

$prOut = ($body | gh pr create --base main --head $branch --title $Title --body-file - 2>&1 | Out-String).Trim()
Write-Output $prOut
$prNum = (gh pr view $branch --json number --jq .number | Out-String).Trim()
Write-Output ("PR_NUMBER=" + $prNum)
Run "checks" { gh pr checks $prNum --watch --interval 10 }
if ($Merge) { Run "merge" { gh pr merge $prNum --squash --delete-branch } }
RunGit "back to main" @("switch", "main")
RunGit "pull" @("pull", "--ff-only")
Write-Output "DONE=PASS"
