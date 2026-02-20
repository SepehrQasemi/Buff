param(
  [string]$ReadyUrl = "http://localhost:8000/api/v1/health/ready"
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
  Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
  Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Fail([string]$Message) {
  Write-Host "[FAIL] $Message" -ForegroundColor Red
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Fail "Docker CLI is not installed or not in PATH."
  exit 1
}

Write-Info "Checking docker compose services."
$composeOutput = & docker compose ps 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Fail "docker compose ps failed."
  $composeOutput | ForEach-Object { Write-Host $_ }
  exit 1
}

$runningLines = @($composeOutput | Where-Object { $_ -match "\brunning\b" -or $_ -match "\bhealthy\b" })
if ($runningLines.Count -eq 0) {
  Write-Fail "No running compose services detected."
  $composeOutput | ForEach-Object { Write-Host $_ }
  exit 1
}

Write-Info "Checking readiness endpoint: $ReadyUrl"
try {
  $readyResponse = Invoke-WebRequest -UseBasicParsing -Uri $ReadyUrl -TimeoutSec 10
} catch {
  Write-Fail "Readiness probe failed: $($_.Exception.Message)"
  exit 1
}

if ($readyResponse.StatusCode -ne 200) {
  Write-Fail "Readiness returned HTTP $($readyResponse.StatusCode)."
  Write-Host $readyResponse.Content
  exit 1
}

$readyPayload = $null
try {
  $readyPayload = $readyResponse.Content | ConvertFrom-Json
} catch {
  $readyPayload = $null
}

if ($null -ne $readyPayload) {
  if ($readyPayload.PSObject.Properties.Name -contains "ready" -and $readyPayload.ready -eq $false) {
    Write-Fail "Readiness payload reports ready=false."
    Write-Host $readyResponse.Content
    exit 1
  }
  if ($readyPayload.PSObject.Properties.Name -contains "ok" -and $readyPayload.ok -eq $false) {
    Write-Fail "Readiness payload reports ok=false."
    Write-Host $readyResponse.Content
    exit 1
  }
}

Write-Ok "Platform readiness check passed."

Write-Info "Installing web dependencies (npm ci)."
& npm --prefix apps/web ci
if ($LASTEXITCODE -ne 0) {
  Write-Fail "npm --prefix apps/web ci failed."
  exit $LASTEXITCODE
}

$tmpLog = Join-Path $env:TEMP ("ui-journey-{0}.log" -f [Guid]::NewGuid().ToString("N"))
Write-Info "Running UI journey."
& npm --prefix apps/web run test:journey 2>&1 | Tee-Object -FilePath $tmpLog
$journeyExit = $LASTEXITCODE

$artifactsPath = ""
if (Test-Path $tmpLog) {
  $artifactMatch = Get-Content $tmpLog |
    Select-String -Pattern '^artifacts:\s*(.+)$' |
    Select-Object -Last 1
  if ($artifactMatch) {
    $artifactsPath = $artifactMatch.Matches[0].Groups[1].Value.Trim()
  }
}

if (Test-Path $tmpLog) {
  Remove-Item $tmpLog -Force
}

if ($artifactsPath) {
  Write-Ok "Artifacts: $artifactsPath"
} else {
  Write-Info "Artifacts path not found in runner output."
}

if ($journeyExit -ne 0) {
  Write-Fail "UI journey failed."
  exit $journeyExit
}

Write-Ok "UI journey passed."
