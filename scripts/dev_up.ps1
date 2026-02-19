param(
  [ValidateSet("up", "down", "logs", "reset-runs")]
  [string]$Action = "up",
  [string[]]$Services
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runsRoot = if ($env:RUNS_ROOT_HOST) { $env:RUNS_ROOT_HOST } else { Join-Path $repoRoot ".runs_compose" }
$resolvedRepo = [System.IO.Path]::GetFullPath($repoRoot)
$resolvedRuns = [System.IO.Path]::GetFullPath($runsRoot)

function Invoke-Compose {
  param([string[]]$Args)
  Push-Location $repoRoot
  try {
    & docker compose @Args
  } finally {
    Pop-Location
  }
}

function Assert-SafeRunsRoot {
  if (-not $resolvedRuns.StartsWith($resolvedRepo, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "reset-runs refused: RUNS_ROOT_HOST must be under repo root ($resolvedRepo)"
  }
  if ($resolvedRuns -eq $resolvedRepo -or $resolvedRuns -eq [System.IO.Path]::GetPathRoot($resolvedRuns)) {
    throw "reset-runs refused: unsafe RUNS_ROOT_HOST ($resolvedRuns)"
  }
}

switch ($Action) {
  "up" {
    New-Item -ItemType Directory -Path $resolvedRuns -Force | Out-Null
    $args = @("up", "-d", "--build")
    if ($Services) {
      $args += $Services
    }
    Invoke-Compose -Args $args
  }
  "down" {
    $args = @("down", "--remove-orphans")
    if ($Services) {
      $args += $Services
    }
    Invoke-Compose -Args $args
  }
  "logs" {
    $args = @("logs", "-f")
    if ($Services) {
      $args += $Services
    }
    Invoke-Compose -Args $args
  }
  "reset-runs" {
    Assert-SafeRunsRoot
    New-Item -ItemType Directory -Path $resolvedRuns -Force | Out-Null
    Get-ChildItem -Path $resolvedRuns -Force | Remove-Item -Recurse -Force
  }
}
