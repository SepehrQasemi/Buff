param(
  [int]$TimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path $PSScriptRoot).Path
$ReadyUrl = "http://localhost:8000/api/v1/health/ready"
$UiUrl = "http://localhost:3000"
$DevUpScript = Join-Path $RepoRoot "scripts/dev_up.ps1"

function Write-Ok([string]$Message) {
  Write-Host "[OK] $Message"
}

function Write-Info([string]$Message) {
  Write-Host "[INFO] $Message"
}

function Write-Fail([string]$Message) {
  Write-Host "[FAIL] $Message"
}

function Coerce-ToArray([object]$Value) {
  if ($null -eq $Value) {
    return @()
  }
  return @($Value)
}

function Get-ObjectPropertyOrDefault([object]$Value, [string]$PropertyName, [object]$DefaultValue) {
  if ($null -eq $Value) {
    return $DefaultValue
  }

  $property = $Value.PSObject.Properties[$PropertyName]
  if ($null -eq $property) {
    return $DefaultValue
  }

  $propertyValue = $property.Value
  if ($null -eq $propertyValue) {
    return $DefaultValue
  }

  return $propertyValue
}

function Test-CommandAvailable([string]$Name) {
  return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-DockerRunning {
  & docker info --format "{{.ServerVersion}}" *> $null
  return $LASTEXITCODE -eq 0
}

function Test-ComposeAvailable {
  & docker compose version *> $null
  return $LASTEXITCODE -eq 0
}

function Get-PortOwners([int]$Port) {
  $owners = @()
  try {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($listeners) {
      foreach ($listener in ($listeners | Sort-Object -Property OwningProcess -Unique)) {
        $procId = [int]$listener.OwningProcess
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $owners += [PSCustomObject]@{
          Port = $Port
          Pid  = $procId
          Name = if ($proc) { $proc.ProcessName } else { "<unknown>" }
          Path = if ($proc -and $proc.Path) { $proc.Path } else { "" }
        }
      }
    }
  } catch {
  }

  if ((@($owners)).Count -gt 0) {
    return $owners
  }

  $netstat = & netstat -ano -p tcp 2>$null
  if (-not $netstat) {
    return @()
  }
  foreach ($line in $netstat) {
    $trimmed = $line.Trim()
    if ($trimmed -notmatch "\s+LISTENING\s+") {
      continue
    }
    if ($trimmed -match "^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$") {
      $linePort = [int]$Matches[1]
      if ($linePort -ne $Port) {
        continue
      }
      $procId = [int]$Matches[2]
      $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
      $owners += [PSCustomObject]@{
        Port = $Port
        Pid  = $procId
        Name = if ($proc) { $proc.ProcessName } else { "<unknown>" }
        Path = if ($proc -and $proc.Path) { $proc.Path } else { "" }
      }
    }
  }
  return ($owners | Sort-Object -Property Port, Pid -Unique)
}

function Get-PortConflicts([int[]]$Ports) {
  $conflicts = @()
  foreach ($port in $Ports) {
    $portOwners = Coerce-ToArray -Value (Get-PortOwners -Port $port)
    foreach ($owner in $portOwners) {
      if ($null -eq $owner) {
        continue
      }
      $conflicts += $owner
    }
  }
  return $conflicts
}

function Show-PortConflicts([object[]]$Conflicts) {
  $normalizedConflicts = Coerce-ToArray -Value $Conflicts
  if ((@($normalizedConflicts)).Count -eq 0) {
    return
  }

  Write-Fail "Required ports are in use."
  foreach ($entry in $normalizedConflicts) {
    $port = Get-ObjectPropertyOrDefault -Value $entry -PropertyName "Port" -DefaultValue "<unknown>"
    $pid = Get-ObjectPropertyOrDefault -Value $entry -PropertyName "Pid" -DefaultValue "<unknown>"
    $name = Get-ObjectPropertyOrDefault -Value $entry -PropertyName "Name" -DefaultValue "<unknown>"
    $path = Get-ObjectPropertyOrDefault -Value $entry -PropertyName "Path" -DefaultValue ""
    $pathSuffix = if ($path) { " [$path]" } else { "" }
    Write-Host ("  - Port {0}: PID {1} ({2}){3}" -f $port, $pid, $name, $pathSuffix)
  }
}

function Read-ErrorResponseBody([System.Exception]$Exception) {
  try {
    $response = $Exception.Response
    if (-not $response) {
      return $Exception.Message
    }
    $stream = $response.GetResponseStream()
    if (-not $stream) {
      return $Exception.Message
    }
    $reader = New-Object System.IO.StreamReader($stream)
    try {
      return $reader.ReadToEnd()
    } finally {
      $reader.Dispose()
      $stream.Dispose()
    }
  } catch {
    return $Exception.Message
  }
}

function Wait-ForReadiness([string]$Url, [int]$TimeoutSeconds) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  $lastBody = ""

  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 5 -ErrorAction Stop
      $body = ($response.Content | Out-String).Trim()
      if ($body) {
        $lastBody = $body
      }
      $payload = $null
      try {
        $payload = $body | ConvertFrom-Json -ErrorAction Stop
      } catch {
      }
      if ($payload -and ($payload.status -eq "ready")) {
        return [PSCustomObject]@{
          Ready = $true
          Body  = $body
        }
      }
    } catch {
      $lastBody = Read-ErrorResponseBody -Exception $_.Exception
    }
    Start-Sleep -Seconds 2
  }

  return [PSCustomObject]@{
    Ready = $false
    Body  = $lastBody
  }
}

function Show-FailureDiagnostics {
  if (-not (Test-DockerRunning)) {
    Write-Fail "Docker is not running. Start Docker Desktop, then run RUN_ME_WINDOWS.bat again."
  }

  if (-not (Test-ComposeAvailable)) {
    Write-Fail "docker compose is not available. Update Docker Desktop to include Compose v2."
  }

  $conflicts = Coerce-ToArray -Value (Get-PortConflicts -Ports @(3000, 8000))
  if ((@($conflicts)).Count -gt 0) {
    Show-PortConflicts -Conflicts $conflicts
  }
}

trap {
  Write-Fail "Unexpected startup error: $($_.Exception.Message)"
  exit 1
}

Write-Info "Starting Buff local platform..."

if (-not (Test-CommandAvailable -Name "docker")) {
  Write-Fail "Docker is not installed. Install Docker Desktop, then run RUN_ME_WINDOWS.bat again."
  exit 1
}

if (-not (Test-DockerRunning)) {
  Write-Fail "Docker is not running. Start Docker Desktop, then run RUN_ME_WINDOWS.bat again."
  exit 1
}

if (-not (Test-ComposeAvailable)) {
  Write-Fail "docker compose is not available. Update Docker Desktop to include Compose v2."
  exit 1
}

$initialConflicts = Coerce-ToArray -Value (Get-PortConflicts -Ports @(3000, 8000))
if ((@($initialConflicts)).Count -gt 0) {
  Show-PortConflicts -Conflicts $initialConflicts
  exit 1
}

if (-not (Test-Path -Path $DevUpScript -PathType Leaf)) {
  Write-Fail "Missing script: scripts/dev_up.ps1"
  exit 1
}

Write-Info "Launching containers with docker compose..."
Push-Location $RepoRoot
try {
  & $DevUpScript up
  if ($LASTEXITCODE -ne 0) {
    Write-Fail "docker compose up failed."
    Show-FailureDiagnostics
    exit 1
  }
} catch {
  Write-Fail "docker compose up failed: $($_.Exception.Message)"
  Show-FailureDiagnostics
  exit 1
} finally {
  Pop-Location
}

Write-Info "Waiting for readiness at $ReadyUrl (timeout: $TimeoutSeconds seconds)..."
$readyResult = Wait-ForReadiness -Url $ReadyUrl -TimeoutSeconds $TimeoutSeconds

if (-not $readyResult.Ready) {
  Write-Fail "Readiness did not become ready before timeout."
  Show-FailureDiagnostics
  if ($readyResult.Body) {
    Write-Host "[INFO] Last /health/ready response: $($readyResult.Body)"
  } else {
    Write-Host "[INFO] Last /health/ready response: <no response>"
  }
  exit 1
}

Write-Ok "Buff is ready."
Write-Ok "UI URL: $UiUrl"
try {
  Start-Process $UiUrl | Out-Null
} catch {
  Write-Info "Could not auto-open browser. Open manually: $UiUrl"
}
