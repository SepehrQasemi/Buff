[CmdletBinding()]
param(
  [string]$Branch = "",
  [string]$Title = "docs: introduce authoritative PROJECT_STATE and system evolution roadmap",
  [string]$Body = "",
  [switch]$BodyFromStdin
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function RunGit([string]$Label, [string[]]$Args) {
  Write-Output ""
  Write-Output ("=== " + $Label + " ===")
  Write-Output ("git " + ($Args -join " "))
  $out = & git @Args 2>&1
  $code = $LASTEXITCODE
  @($out) | ForEach-Object { Write-Output $_ }
  if ($code -ne 0) { throw ("FAIL(" + $Label + "): exit=" + $code + " cmd=git " + ($Args -join " ")) }
  return $out
}

function RunCmd([string]$Label, [scriptblock]$Script, [switch]$AllowRgNoMatch) {
  Write-Output ""
  Write-Output ("=== " + $Label + " ===")
  $out = & $Script 2>&1
  $code = $LASTEXITCODE
  @($out) | ForEach-Object { Write-Output $_ }
  if ($AllowRgNoMatch) {
    if ($code -gt 1) { throw ("FAIL(" + $Label + "): exit=" + $code) }
  } else {
    if ($code -ne 0) { throw ("FAIL(" + $Label + "): exit=" + $code) }
  }
  return $out
}

function RepoRoot() {
  $r = (& git rev-parse --show-toplevel 2>$null | Out-String).Trim()
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($r)) { throw "Unable to resolve repo root." }
  return [System.IO.Path]::GetFullPath($r)
}

function AssertUnderRepo([string]$RepoRoot, [string]$RelativePath) {
  $full = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $RelativePath))
  if (-not $full.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw ("Path escapes repo root: " + $RelativePath)
  }
  return $full
}

function GhPrFieldByBranch([string]$BranchName, [string]$Fields, [string]$Jq) {
  $out = & gh pr view $BranchName --json $Fields --jq $Jq 2>$null
  if ($LASTEXITCODE -ne 0) { return $null }
  $v = ($out | Out-String).Trim()
  if ([string]::IsNullOrWhiteSpace($v)) { return $null }
  return $v
}

function RequireDocsOnly([string[]]$Paths) {
  $bad = @()
  foreach ($p in $Paths) {
    $pp = ($p -replace "\\", "/")
    if (($pp -ne "README.md") -and (-not $pp.StartsWith("docs/"))) { $bad += $pp }
  }
  Write-Output "STAGED_FILES:"
  $Paths | ForEach-Object { Write-Output (($_ -replace "\\", "/")) }
  Write-Output "BAD_STAGED_FILES:"
  $bad | ForEach-Object { Write-Output $_ }
  if ($bad.Count -gt 0) { throw "Scope violation: non-doc files staged." }
  Write-Output "DOCS_ONLY_SCOPE=PASS"
}

function RunRunbookOnly([string]$Label, [string]$Needle) {
  $out = RunCmd $Label { & rg -n --fixed-strings $Needle docs }
  $offenders = @()
  foreach ($line in @($out)) {
    if ($line -match "^(docs[\\/][^:]+):") {
      $path = ($Matches[1] -replace "\\", "/")
      if ($path -ne "docs/05_RUNBOOK_DEV_WORKFLOW.md") { $offenders += $line }
    }
  }
  if ($offenders.Count -gt 0) {
    Write-Output "RUNBOOK_ONLY_VIOLATIONS:"
    $offenders | ForEach-Object { Write-Output $_ }
    throw ("Single-source violation for needle: " + $Needle)
  }
}

$root = RepoRoot
Set-Location $root
AssertUnderRepo $root "README.md" | Out-Null
AssertUnderRepo $root "docs" | Out-Null
AssertUnderRepo $root "scripts/docs_pr_autopilot.ps1" | Out-Null
Write-Output ("REPO_ROOT=" + $root)
Write-Output "REPO_ROOT_GUARD=PASS"

if ([string]::IsNullOrWhiteSpace($Branch)) { throw "Branch is required (pass -Branch)." }

if ($BodyFromStdin) {
  $stdinBody = [Console]::In.ReadToEnd()
  if (-not [string]::IsNullOrWhiteSpace($stdinBody)) { $Body = $stdinBody }
}
if ([string]::IsNullOrWhiteSpace($Body)) { throw "PR body required. Pipe body and use -BodyFromStdin." }

RunGit "fetch origin" @("fetch", "origin", "--prune") | Out-Null

& git show-ref --verify --quiet ("refs/heads/" + $Branch)
$hasLocal = ($LASTEXITCODE -eq 0)
$remoteLine = (& git ls-remote --heads origin $Branch 2>$null | Out-String).Trim()
$hasRemote = -not [string]::IsNullOrWhiteSpace($remoteLine)

if ($hasLocal) { RunGit "switch local branch" @("switch", $Branch) | Out-Null }
elseif ($hasRemote) { RunGit "create tracking branch" @("switch", "-c", $Branch, "--track", ("origin/" + $Branch)) | Out-Null }
else { RunGit "create new branch" @("switch", "-c", $Branch) | Out-Null }

RunGit "status" @("status", "-sb") | Out-Null

$statusPorcelain = RunGit "status porcelain" @("status", "--porcelain")
$worktreePaths = @()
foreach ($line in @($statusPorcelain)) {
  $text = ($line | Out-String).TrimEnd()
  if ([string]::IsNullOrWhiteSpace($text)) { continue }
  if ($text.Length -lt 4) { continue }
  $pathPart = $text.Substring(3).Trim()
  if ($pathPart -match " -> ") { $pathPart = ($pathPart -split " -> ")[-1].Trim() }
  if (-not [string]::IsNullOrWhiteSpace($pathPart)) { $worktreePaths += ($pathPart -replace "\\", "/") }
}
$worktreePaths = @($worktreePaths | Sort-Object -Unique)

$offenders = @($worktreePaths | Where-Object { ($_ -ne "README.md") -and (-not $_.StartsWith("docs/")) } | Sort-Object -Unique)
if ($offenders.Count -gt 0) {
  if (($offenders.Count -eq 1) -and ($offenders[0] -eq "scripts/docs_pr_autopilot.ps1")) {
    Write-Output "NON_SCOPE_CHANGE_DETECTED=scripts/docs_pr_autopilot.ps1 (ignored)"
  } else {
    Write-Output "SCOPE_OFFENDERS:"
    $offenders | ForEach-Object { Write-Output $_ }
    throw "SCOPE_VIOLATION_WORKTREE"
  }
}

$stageCandidates = @($worktreePaths | Where-Object { ($_ -eq "README.md") -or ($_.StartsWith("docs/")) } | Sort-Object -Unique)
foreach ($p in $stageCandidates) {
  RunGit ("stage " + $p) @("add", "--", $p) | Out-Null
}

$stagedLines = RunGit "staged names" @("diff", "--cached", "--name-only")
$staged = @()
foreach ($line in @($stagedLines)) {
  $name = ($line | Out-String).Trim()
  if (-not [string]::IsNullOrWhiteSpace($name)) { $staged += ($name -replace "\\", "/") }
}
RequireDocsOnly $staged

if ($staged.Count -gt 0) { RunGit "commit" @("commit", "-m", "docs: introduce authoritative project state + system evolution roadmap") | Out-Null }
else { Write-Output "NO_STAGED_CHANGES=SKIP_COMMIT" }

RunGit "show stat" @("show", "--stat", "HEAD") | Out-Null
RunGit "diff cached" @("diff", "--cached", "--name-only") | Out-Null
RunGit "push" @("push", "-u", "origin", $Branch) | Out-Null

$prUrl = GhPrFieldByBranch $Branch "url" ".url"
if ($prUrl) {
  Write-Output ("PR_ALREADY_EXISTS=" + $prUrl)
} else {
  Write-Output "Creating PR..."
  $createOut = $Body | & gh pr create --base main --head $Branch --title $Title --body-file - 2>&1
  $txt = ($createOut | Out-String).Trim()
  if ($LASTEXITCODE -ne 0) {
    if ($txt -match "already exists:\s*(https://\S+)") { $prUrl = $Matches[1]; Write-Output ("PR_ALREADY_EXISTS=" + $prUrl) }
    else { Write-Output $txt; throw "FAIL(PR_CREATE)" }
  } else {
    Write-Output $txt
    if ($txt -match "https://\S+") { $prUrl = $Matches[0] }
  }
}

$prNumber = GhPrFieldByBranch $Branch "number" ".number"
if (-not $prNumber) { throw "Cannot resolve PR number for branch." }
if (-not $prUrl) { $prUrl = GhPrFieldByBranch $Branch "url" ".url" }
if (-not $prUrl) { $prUrl = "" }
Write-Output ("PR_NUMBER=" + $prNumber)

RunCmd "header: Normative Authority" { & rg -n "## Normative Authority" docs/PRODUCT_SPEC.md } | Out-Null
RunCmd "header: Runtime Contract Alignment" { & rg -n "## Runtime Contract Alignment" docs/UI_SPEC.md } | Out-Null
RunCmd "header: Hard Safety Constraints" { & rg -n "## Hard Safety Constraints" docs/USER_EXTENSIBILITY.md } | Out-Null
RunCmd "header: Contract And Safety Constraints" { & rg -n "## Contract And Safety Constraints" docs/CHATBOT_SPEC.md } | Out-Null
RunCmd "header: Contract Alignment" { & rg -n "## Contract Alignment" docs/STRATEGY_CONTRACT.md docs/INDICATOR_CONTRACT.md docs/RISK_MODEL_SPEC.md docs/STRATEGY_PACK_SPEC.md } | Out-Null

RunRunbookOnly "cmd: dev_start" "python scripts/dev_start.py"
RunRunbookOnly "cmd: verify_phase1" "python scripts/verify_phase1.py --with-services"
RunRunbookOnly "cmd: release_gate" "python -m tools.release_gate"
RunRunbookOnly "cmd: release_preflight" "python -m tools.release_preflight"
RunRunbookOnly "cmd: export_report" "python scripts/export_report.py"
RunRunbookOnly "cmd: feed_generate" "src.paper.feed_generate"
RunRunbookOnly "cmd: cli_long_run" "src.paper.cli_long_run"

RunCmd "replacement-char scan (exit 1 ok)" { & rg -n "�" docs -g "*.md"; Write-Output ("RG_EXIT_CODE=" + $LASTEXITCODE) } -AllowRgNoMatch | Out-Null
RunCmd "canonical wiring runbook" { & rg -n "canonical-error-schema" docs/05_RUNBOOK_DEV_WORKFLOW.md } | Out-Null
RunCmd "canonical wiring contracts" { & rg -n "canonical-error-schema" docs/03_CONTRACTS_AND_SCHEMAS.md } | Out-Null

Write-Output ""
Write-Output "=== gh pr checks ==="
$checksOut = & gh pr checks $prNumber 2>&1
@($checksOut) | ForEach-Object { Write-Output $_ }

$sha = (& git rev-parse --short HEAD | Out-String).Trim()
Write-Output ""
Write-Output "=== SUMMARY ==="
Write-Output ("BRANCH=" + $Branch)
Write-Output ("HEAD_SHA=" + $sha)
Write-Output ("PR_URL=" + $prUrl)
Write-Output ("PR_NUMBER=" + $prNumber)
Write-Output "DOCS_ONLY_SCOPE=PASS"
Write-Output "DONE=PASS"
