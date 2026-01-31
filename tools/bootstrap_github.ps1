# Bootstrap GitHub project hygiene for Buff-Trading-AI/Buff
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-GhAuth {
  $gh = Get-Command gh -ErrorAction SilentlyContinue
  if (-not $gh) {
    throw "GitHub CLI (gh) not found in PATH."
  }
  try {
    gh auth status | Out-Null
  } catch {
    throw "GitHub CLI (gh) is not authenticated. Run 'gh auth login'."
  }
}

$Owner = 'Buff-Trading-AI'
$Repo = 'Buff'
$RepoFull = "$Owner/$Repo"

function Get-PropValue {
  param(
    [object]$Obj,
    [string]$Name
  )
  if ($null -eq $Obj) { return $null }
  if ($Obj -is [string]) { return $null }
  if ($Obj -is [System.Collections.IDictionary]) {
    if ($Obj.Contains($Name)) { return $Obj[$Name] }
    foreach ($key in $Obj.Keys) {
      if ($key -is [string] -and $key.Equals($Name, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $Obj[$key]
      }
    }
  }
  $prop = $Obj.PSObject.Properties | Where-Object { $_.Name -ieq $Name } | Select-Object -First 1
  if ($prop) { return $prop.Value }
  return $null
}

function Normalize-Title {
  param([string]$Text)
  if ($null -eq $Text) { return $null }
  $normalized = $Text -replace '[\u2012\u2013\u2014\u2212]', '-'
  $normalized = $normalized -replace '\s+', ' '
  return $normalized.Trim()
}

function Normalize-TitleKey {
  param([string]$Text)
  if ($null -eq $Text) { return $null }
  $normalized = $Text.ToString().Normalize([System.Text.NormalizationForm]::FormKC)
  $normalized = $normalized.ToLowerInvariant()
  $normalized = $normalized -replace '[^a-z0-9]+', ''
  return $normalized
}

function Get-AllMilestones {
  $milestones = @()
  foreach ($state in @('open', 'closed')) {
    $page = 1
    while ($true) {
      $batch = gh api "/repos/$Owner/$Repo/milestones?state=$state&per_page=100&page=$page" | ConvertFrom-Json
      if ($null -eq $batch) { break }
      if ($batch -isnot [System.Array]) { $batch = @($batch) }
      if ($batch.Count -eq 0) { break }
      $milestones += $batch
      $page++
    }
  }
  return $milestones
}

function Get-AllLabels {
  $labels = @()
  $page = 1
  while ($true) {
    $batch = gh api "/repos/$Owner/$Repo/labels?per_page=100&page=$page" | ConvertFrom-Json
    if ($null -eq $batch) { break }
    if ($batch -isnot [System.Array]) { $batch = @($batch) }
    if ($batch.Count -eq 0) { break }
    $labels += $batch
    $page++
  }
  return $labels
}

function Get-AllIssues {
  $issues = @()
  $page = 1
  while ($true) {
    $batch = gh api "/repos/$Owner/$Repo/issues?state=all&per_page=100&page=$page" | ConvertFrom-Json
    if ($null -eq $batch) { break }
    if ($batch -isnot [System.Array]) { $batch = @($batch) }
    $batch = $batch | Where-Object { -not (Get-PropValue $_ 'pull_request') }
    $batch = @($batch)
    if ($batch.Count -eq 0) { break }
    $issues += $batch
    $page++
  }
  return $issues
}

function Ensure-Milestone {
  param(
    [string]$Title,
    [string]$Description,
    [array]$ExistingMilestones,
    [ref]$CreatedList
  )
  $targetTitle = Normalize-Title $Title
  $targetKey = Normalize-TitleKey $Title
  $found = $ExistingMilestones | Where-Object {
    $title = Get-PropValue $_ 'title'
    $number = Get-PropValue $_ 'number'
    $title -and $number -and ((Normalize-Title $title) -eq $targetTitle -or (Normalize-TitleKey $title) -eq $targetKey)
  }
  if ($found) { return $found[0] }

  $payload = @{ title = $Title; description = $Description } | ConvertTo-Json
  $created = $null
  $createError = $null
  try {
    $created = gh api -X POST "/repos/$Owner/$Repo/milestones" -H "Accept: application/vnd.github+json" -f title=$Title -f description=$Description | ConvertFrom-Json
  } catch {
    $createError = $_
  }
  if ($null -ne (Get-PropValue $created 'number')) {
    $CreatedList.Value += $created
    return $created
  }

  $refreshed = Get-AllMilestones
  $fallback = $refreshed | Where-Object {
    $title = Get-PropValue $_ 'title'
    $number = Get-PropValue $_ 'number'
    $title -and $number -and ((Normalize-Title $title) -eq $targetTitle -or (Normalize-TitleKey $title) -eq $targetKey)
  }
  if ($fallback) { return $fallback[0] }

  $createdText = if ($created) { ($created | ConvertTo-Json -Depth 6) } elseif ($createError) { $createError.Exception.Message } else { 'Unknown error' }
  throw "Milestone create failed for '$Title'. Response: $createdText"
}

function Ensure-Label {
  param(
    [string]$Name,
    [array]$ExistingLabels,
    [ref]$CreatedList
  )
  $found = $ExistingLabels | Where-Object { (Get-PropValue $_ 'name') -eq $Name }
  if ($found) { return $found[0] }

  $color = (Get-Random -Minimum 0 -Maximum 16777215).ToString('X6')
  $created = gh api -X POST "/repos/$Owner/$Repo/labels" -H "Accept: application/vnd.github+json" -f name=$Name -f color=$color | ConvertFrom-Json
  $CreatedList.Value += $created
  return $created
}

function Ensure-Issue {
  param(
    [string]$Title,
    [string]$Body,
    [int]$MilestoneNumber,
    [string[]]$Labels,
    [array]$ExistingIssues,
    [ref]$CreatedList
  )
  $found = $ExistingIssues | Where-Object { (Get-PropValue $_ 'title') -eq $Title }
  if ($found) { return $found[0] }

  $payload = @{
    title = $Title
    body = $Body
    milestone = $MilestoneNumber
    labels = $Labels
  } | ConvertTo-Json -Depth 6
  $created = $payload | gh api -X POST "/repos/$Owner/$Repo/issues" -H "Accept: application/vnd.github+json" --input - | ConvertFrom-Json
  $CreatedList.Value += $created
  return $created
}

Assert-GhAuth

$existingMilestones = Get-AllMilestones
$existingLabels = Get-AllLabels
$existingIssues = Get-AllIssues

$createdMilestones = @()
$createdLabels = @()
$createdIssues = @()

$milestonesSpec = @(
  @{ Title = 'M1 — Data Pipeline'; Description = 'Deterministic OHLCV ingest, validation, resampling, storage.' },
  @{ Title = 'M2 — Knowledge Base'; Description = 'Machine-readable rules/knowledge extraction + tests.' },
  @{ Title = 'M3 — Features / Indicators'; Description = 'Deterministic indicators registry + feature sets.' },
  @{ Title = 'M4 — Risk / Permission Layer'; Description = 'GREEN/YELLOW/RED risk veto + contracts.' },
  @{ Title = 'M5 — Strategy Registry + Selector'; Description = 'Registered strategies only, deterministic selection.' },
  @{ Title = 'M6 — Execution Engine (Paper)'; Description = 'Paper execution state machine + idempotency + kill switch.' },
  @{ Title = 'M7 — Interface (Read-only UI/Chatbot)'; Description = 'Read-only UI/chatbot, reports, no execution.' }
)

$milestoneMap = @{}
foreach ($m in $milestonesSpec) {
  $ms = Ensure-Milestone -Title $m.Title -Description $m.Description -ExistingMilestones $existingMilestones -CreatedList ([ref]$createdMilestones)
  $milestoneMap[$m.Title] = $ms
}

$labelNames = @('bug','enhancement','docs','security','ci','tests','refactor','data','risk','execution')
foreach ($name in $labelNames) {
  Ensure-Label -Name $name -ExistingLabels $existingLabels -CreatedList ([ref]$createdLabels) | Out-Null
}

$nonGoals = "Non-goals:\n- No prediction\n- No buy/sell signals\n- No strategy invention/optimization"

function New-IssueBody {
  param(
    [string]$Problem,
    [string[]]$Criteria
  )
  $criteriaText = ($Criteria | ForEach-Object { "- $_" }) -join "`n"
  return @(
    "Problem",
    $Problem,
    "",
    "Acceptance criteria",
    $criteriaText,
    "",
    $nonGoals
  ) -join "`n"
}

$issuesSpec = @(
  @{ Title = 'Risk inputs contract (typed schema)'; Milestone = 'M4 — Risk / Permission Layer'; Problem = "Define the typed schema for all risk inputs used by the veto layer.\nEnsure it is deterministic and versioned for audits."; Criteria = @('Schema is explicit and validated at boundaries','Versioning strategy documented','Round-trip serialization test added') },
  @{ Title = 'Risk state machine (GREEN/YELLOW/RED + tests)'; Milestone = 'M4 — Risk / Permission Layer'; Problem = "Implement deterministic state transitions for GREEN/YELLOW/RED.\nInclude tests for all transition paths and edge cases."; Criteria = @('Explicit transition table implemented','Tests cover all transitions','Invalid transitions are rejected') },
  @{ Title = 'Risk veto integration point'; Milestone = 'M4 — Risk / Permission Layer'; Problem = "Add a single integration point where risk can veto execution.\nIt must be fail-closed and auditable."; Criteria = @('Integration point is centralized','Fail-closed behavior verified','Decision is logged with inputs/outputs') },
  @{ Title = 'Strategy registry interface (register/list/validate)'; Milestone = 'M5 — Strategy Registry + Selector'; Problem = "Define a registry interface for strategies.\nOnly registered strategies can be selected."; Criteria = @('Register/list/validate API defined','Validation checks mandatory fields','Unauthorized strategies rejected') },
  @{ Title = 'Selector contract (deterministic I/O + audit fields)'; Milestone = 'M5 — Strategy Registry + Selector'; Problem = "Define deterministic selector inputs/outputs with audit fields.\nEnsure selection is reproducible."; Criteria = @('I/O schema documented','Audit fields include inputs and decision basis','Determinism enforced in tests') },
  @{ Title = 'Order intent model (paper)'; Milestone = 'M6 — Execution Engine (Paper)'; Problem = "Create a paper-order intent model that captures required fields.\nIt must be serializable and deterministic."; Criteria = @('Model fields defined and validated','Serialization round-trip test','Deterministic defaults documented') },
  @{ Title = 'Idempotency keying (dedupe protection)'; Milestone = 'M6 — Execution Engine (Paper)'; Problem = "Define idempotency keys for paper execution requests.\nPrevent duplicate processing in retries."; Criteria = @('Key generation spec defined','Duplicate requests deduped','Tests cover retry scenarios') },
  @{ Title = 'Kill switch wiring (fail-closed)'; Milestone = 'M6 — Execution Engine (Paper)'; Problem = "Wire a kill switch that stops paper execution.\nSystem must fail-closed when triggered."; Criteria = @('Kill switch can be triggered deterministically','Fail-closed behavior verified','Trigger reason logged') },
  @{ Title = 'Audit log schema (event id + decision trace)'; Milestone = 'M4 — Risk / Permission Layer'; Problem = "Define an audit log schema for decisions and events.\nInclude event ids and decision traces."; Criteria = @('Event id format defined','Decision trace includes inputs/outputs','Schema documented for consumers') },
  @{ Title = 'CLI: report generator (reads logs, outputs summary)'; Milestone = 'M7 — Interface (Read-only UI/Chatbot)'; Problem = "Create a CLI report generator that reads audit logs.\nIt outputs a deterministic summary."; Criteria = @('CLI reads log files and validates schema','Summary output is deterministic','Report includes risk decisions and outcomes') }
)

foreach ($spec in $issuesSpec) {
  $ms = $milestoneMap[$spec.Milestone]
  $msNumber = Get-PropValue $ms 'number'
  if ($null -eq $msNumber) {
    $msText = ($ms | ConvertTo-Json -Depth 6)
    throw "Milestone '$($spec.Milestone)' not found or missing number. Value: $msText"
  }
  $labels = switch ($spec.Milestone) {
    'M4 — Risk / Permission Layer' { @('risk','enhancement') }
    'M5 — Strategy Registry + Selector' { @('enhancement') }
    'M6 — Execution Engine (Paper)' { @('execution','enhancement') }
    'M7 — Interface (Read-only UI/Chatbot)' { @('docs','enhancement') }
    default { @() }
  }
  $body = New-IssueBody -Problem $spec.Problem -Criteria $spec.Criteria
  Ensure-Issue -Title $spec.Title -Body $body -MilestoneNumber $msNumber -Labels $labels -ExistingIssues $existingIssues -CreatedList ([ref]$createdIssues) | Out-Null
}

if ($createdMilestones.Count -gt 0) {
  Write-Host "Created milestones:" -ForegroundColor Cyan
  foreach ($m in $createdMilestones) {
    Write-Host ("- {0} #{1} {2}" -f $m.title, $m.number, $m.html_url)
  }
} else {
  Write-Host "Created milestones: none"
}

if ($createdLabels.Count -gt 0) {
  Write-Host "Created labels:" -ForegroundColor Cyan
  foreach ($l in $createdLabels) {
    Write-Host ("- {0}" -f $l.name)
  }
} else {
  Write-Host "Created labels: none"
}

if ($createdIssues.Count -gt 0) {
  Write-Host "Created issues:" -ForegroundColor Cyan
  foreach ($i in $createdIssues) {
    Write-Host ("- {0} {1}" -f $i.title, $i.html_url)
  }
} else {
  Write-Host "Created issues: none"
}
