param(
  [int]$ApiPort = 8000,
  [int]$UiPort = 3000,
  [string]$RunId = "stage5_demo"
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$artifactsRoot = Join-Path $repoRoot "tests\fixtures\artifacts"

$pythonBin = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonBin)) {
  $pythonBin = "python"
}

$env:ARTIFACTS_ROOT = $artifactsRoot
$env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:$ApiPort/api/v1"
if (Test-Path Env:RUNS_ROOT) {
  Remove-Item Env:RUNS_ROOT
}

Write-Host "Starting Stage-5 demo API..."
$apiProc = Start-Process -PassThru -FilePath $pythonBin -ArgumentList @(
  "-m",
  "uvicorn",
  "apps.api.main:app",
  "--host",
  "127.0.0.1",
  "--port",
  $ApiPort,
  "--reload"
) -WorkingDirectory $repoRoot

Write-Host "Starting Stage-5 demo Web UI..."
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
  $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
}
if (-not $npm) {
  Write-Error "npm not found on PATH. Install Node.js (includes npm) or add it to PATH."
  if ($apiProc -and -not $apiProc.HasExited) {
    Stop-Process -Id $apiProc.Id -Force
  }
  exit 1
}

$uiProc = $null
try {
  if ($npm.Source -match "\.cmd$") {
    $uiProc = Start-Process -PassThru -FilePath "cmd.exe" -ArgumentList @(
      "/c",
      $npm.Source,
      "run",
      "dev",
      "--",
      "--port",
      "$UiPort"
    ) -WorkingDirectory (Join-Path $repoRoot "apps\web")
  } else {
    $uiProc = Start-Process -PassThru -FilePath $npm.Source -ArgumentList @(
      "run",
      "dev",
      "--",
      "--port",
      "$UiPort"
    ) -WorkingDirectory (Join-Path $repoRoot "apps\web")
  }
} catch {
  Write-Error "Failed to start Web UI. Ensure Node.js/npm is installed and on PATH."
  Write-Error $_
  if ($apiProc -and -not $apiProc.HasExited) {
    Stop-Process -Id $apiProc.Id -Force
  }
  exit 1
}

if (-not $uiProc -or -not $uiProc.Id) {
  Write-Error "UI process did not start."
  if ($apiProc -and -not $apiProc.HasExited) {
    Stop-Process -Id $apiProc.Id -Force
  }
  exit 1
}

Write-Host "Stage-5 demo running (read-only)"
Write-Host "Open http://localhost:$UiPort/runs/$RunId"

try {
  Wait-Process -Id $uiProc.Id
} finally {
  if ($uiProc -and -not $uiProc.HasExited) {
    Stop-Process -Id $uiProc.Id -Force -ErrorAction SilentlyContinue
  }
  if ($apiProc -and -not $apiProc.HasExited) {
    Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
  }
}
