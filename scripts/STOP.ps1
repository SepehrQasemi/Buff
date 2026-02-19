Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DevUpScript = Join-Path $RepoRoot "scripts/dev_up.ps1"

function Write-Ok([string]$Message) {
  Write-Host "[OK] $Message"
}

function Write-Fail([string]$Message) {
  Write-Host "[FAIL] $Message"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Fail "Docker is not installed."
  exit 1
}

& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Fail "docker compose is not available."
  exit 1
}

if (-not (Test-Path -Path $DevUpScript -PathType Leaf)) {
  Write-Fail "Missing script: scripts/dev_up.ps1"
  exit 1
}

Write-Host "[INFO] Stopping Buff containers..."
Push-Location $RepoRoot
try {
  & $DevUpScript down
  if ($LASTEXITCODE -ne 0) {
    Write-Fail "Failed to stop Buff containers."
    exit 1
  }
} finally {
  Pop-Location
}

Write-Ok "Buff services stopped."
Write-Ok "Existing run data was not deleted."
