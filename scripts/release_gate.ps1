Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:RepoRoot = (git rev-parse --show-toplevel).Trim()
$script:ReportsDir = Join-Path $script:RepoRoot "reports"
$script:UiWorkspaceMarker = 'data-testid="chart-workspace"'

function Get-ListeningPids([int[]]$Ports) {
    $pids = @()
    foreach ($port in $Ports) {
        $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $connections) {
            if ($null -ne $conn.OwningProcess) {
                $pids += [int]$conn.OwningProcess
            }
        }
    }
    return $pids | Sort-Object -Unique
}

function Stop-ListeningPids([int[]]$Ports) {
    $pids = Get-ListeningPids -Ports $Ports
    foreach ($procId in $pids) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
        } catch {
            Write-Host "WARN: Failed to stop PID ${procId}: $($_.Exception.Message)"
        }
    }
}

function Get-NextDevProcesses {
    $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "node" -and $_.CommandLine -match "next" -and $_.CommandLine -match "dev" })
    return $procs
}

function Clear-NextDevLock {
    $lockPath = Join-Path $script:RepoRoot "apps/web/.next/dev/lock"
    if (-not (Test-Path $lockPath)) {
        return
    }
    $nextProcs = Get-NextDevProcesses
    if ($null -ne $nextProcs -and $nextProcs.Count -gt 0) {
        Write-Host "WARN: next dev appears to be running; skipping lock removal."
        return
    }
    Remove-Item -Path $lockPath -Force
}

function Start-Api {
    $env:ARTIFACTS_ROOT = "tests/fixtures/artifacts"
    $args = @("-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8000")
    return Start-Process -FilePath "python" -ArgumentList $args -WorkingDirectory $script:RepoRoot -PassThru -WindowStyle Hidden
}

function Test-PortFree([int]$Port) {
    $inUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return ($null -eq $inUse -or $inUse.Count -eq 0)
}

function Start-Ui {
    $env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000/api/v1"
    $ports = @(3000, 3001)
    $port = $null
    foreach ($candidate in $ports) {
        if (Test-PortFree -Port $candidate) {
            $port = $candidate
            break
        }
    }
    if ($null -eq $port) {
        throw "No free UI port found (3000/3001)"
    }
    $webRoot = Join-Path $script:RepoRoot "apps/web"
    $nextCmd = Join-Path $webRoot "node_modules/.bin/next.cmd"
    $nextJs = Join-Path $webRoot "node_modules/next/dist/bin/next"
    if (Test-Path $nextCmd) {
        $filePath = $nextCmd
        $args = @("dev", "--port", "$port")
    } elseif (Test-Path $nextJs) {
        $filePath = "node"
        $args = @($nextJs, "dev", "--port", "$port")
    } else {
        throw "next dev binary not found; install deps in apps/web"
    }
    $proc = Start-Process -FilePath $filePath -ArgumentList $args -WorkingDirectory $webRoot -PassThru -NoNewWindow
    return [pscustomobject]@{ Process = $proc; Port = $port }
}

function Wait-Http200([string[]]$Urls, [int]$TimeoutSeconds) {
    $start = Get-Date
    foreach ($url in $Urls) {
        $ok = $false
        while (-not $ok) {
            try {
                $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
                if ($response.StatusCode -eq 200) {
                    $ok = $true
                    break
                }
            } catch {
                Start-Sleep -Milliseconds 500
            }
            if ((Get-Date) - $start -gt [TimeSpan]::FromSeconds($TimeoutSeconds)) {
                throw "Timed out waiting for 200 from $url"
            }
        }
    }
}

function Invoke-LoggedProcess(
    [string]$Label,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [int]$TimeoutSeconds = 0,
    [string]$WorkingDirectory = $script:RepoRoot
) {
    Write-Host "`n==> $Label"
    $timedOut = $false
    if ($TimeoutSeconds -le 0) {
        Push-Location $WorkingDirectory
        $output = & $FilePath @ArgumentList 2>&1 | Tee-Object -Variable capture
        $exit = $LASTEXITCODE
        Pop-Location
        return [pscustomobject]@{
            ExitCode = $exit
            TimedOut = $false
            Output   = ($capture -join "`n")
        }
    }

    $job = Start-Job -ScriptBlock {
        param($Path, $Args, $Workdir)
        Push-Location $Workdir
        $output = & $Path @Args 2>&1
        $exit = $LASTEXITCODE
        Pop-Location
        [pscustomobject]@{ Output = ($output -join "`n"); ExitCode = $exit }
    } -ArgumentList $FilePath, $ArgumentList, $WorkingDirectory

    $completed = Wait-Job $job -Timeout $TimeoutSeconds
    if ($null -eq $completed) {
        $timedOut = $true
        Stop-Job $job -Force | Out-Null
        $result = [pscustomobject]@{ Output = ""; ExitCode = 124 }
    } else {
        $result = Receive-Job $job
    }
    Remove-Job $job -Force | Out-Null
    Write-Host $result.Output
    return [pscustomobject]@{
        ExitCode = $result.ExitCode
        TimedOut = $timedOut
        Output   = $result.Output
    }
}

function Detect-UiPort {
    foreach ($port in @(3000, 3001)) {
        $url = "http://127.0.0.1:$port/runs/phase1_demo"
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200 -and $response.Content -match $script:UiWorkspaceMarker) {
                return $port
            }
        } catch {}
    }
    return $null
}

function Run-UiSmoke([int]$UiPort) {
    $env:ARTIFACTS_ROOT = "tests/fixtures/artifacts"
    $env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000/api/v1"
    $env:UI_BASE = "http://127.0.0.1:$UiPort"
    return Invoke-LoggedProcess -Label "ui-smoke" -FilePath "node" -ArgumentList @("apps/web/scripts/ui-smoke.mjs")
}

function Run-RuffPytest {
    $ruff = Invoke-LoggedProcess -Label "ruff check" -FilePath "python" -ArgumentList @("-m", "ruff", "check", ".")
    $pytest = Invoke-LoggedProcess -Label "pytest -q (timeout 600s)" -FilePath "python" -ArgumentList @("-m", "pytest", "-q") -TimeoutSeconds 600
    if ($pytest.TimedOut) {
        $pytest = Invoke-LoggedProcess -Label "pytest -q (retry 1200s)" -FilePath "python" -ArgumentList @("-m", "pytest", "-q") -TimeoutSeconds 1200
    }
    return [pscustomobject]@{ Ruff = $ruff; Pytest = $pytest }
}

function TeardownByPorts([int[]]$Ports) {
    Stop-ListeningPids -Ports $Ports
}

function Write-ProofReport([string]$Path, [hashtable]$Data) {
    if (-not (Test-Path $script:ReportsDir)) {
        New-Item -ItemType Directory -Path $script:ReportsDir | Out-Null
    }
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# Release Gate Proof Report")
    $lines.Add("")
    $lines.Add("## HEAD / origin")
    $lines.Add("HEAD: $($Data.HeadSha)")
    $lines.Add("origin/main: $($Data.OriginSha)")
    $lines.Add("")
    foreach ($key in $Data.Logs.Keys) {
        $lines.Add("## $key")
        $lines.Add('```text')
        $lines.Add($Data.Logs[$key])
        $lines.Add('```')
        $lines.Add("")
    }
    $lines.Add("## Final Verdict")
    $lines.Add($Data.Verdict)
    $lines.Add("")
    $lines | Set-Content -Path $Path -Encoding UTF8
}

function Main {
    $ports = @(3000, 3001, 8000)
    $logs = @{}
    $verdict = "NO-GO"

    Stop-ListeningPids -Ports $ports
    Clear-NextDevLock

    $headSha = (git rev-parse HEAD).Trim()
    $originSha = (git rev-parse origin/main).Trim()

    $verify = Invoke-LoggedProcess -Label "verify_phase1 --with-services --no-teardown" -FilePath "python" -ArgumentList @("scripts/verify_phase1.py", "--with-services", "--no-teardown") -TimeoutSeconds 3600
    $logs["verify_phase1 --with-services --no-teardown"] = $verify.Output

    $uiPort = Detect-UiPort
    if ($null -eq $uiPort) {
        Write-Host "UI not detected on 3000/3001; attempting to start UI."
        $ui = Start-Ui
        $uiPort = $ui.Port
    }

    Wait-Http200 -Urls @("http://127.0.0.1:8000/api/v1/health") -TimeoutSeconds 60
    $uiSmoke = Run-UiSmoke -UiPort $uiPort
    $logs["ui-smoke"] = $uiSmoke.Output

    $ruffPy = Run-RuffPytest
    $logs["ruff check"] = $ruffPy.Ruff.Output
    $logs["pytest -q"] = $ruffPy.Pytest.Output

    $verifyCode = if ($null -eq $verify.ExitCode) { 1 } else { [int]$verify.ExitCode }
    $uiSmokeCode = if ($null -eq $uiSmoke.ExitCode) { 1 } else { [int]$uiSmoke.ExitCode }
    $ruffCode = if ($null -eq $ruffPy.Ruff.ExitCode) { 1 } else { [int]$ruffPy.Ruff.ExitCode }
    $pytestCode = if ($null -eq $ruffPy.Pytest.ExitCode) { 1 } else { [int]$ruffPy.Pytest.ExitCode }
    $logs["exit-codes"] = "verify_phase1=$verifyCode`nui-smoke=$uiSmokeCode`nruff=$ruffCode`npytest=$pytestCode"

    $allOk = ($verifyCode -eq 0) -and ($uiSmokeCode -eq 0) -and ($ruffCode -eq 0) -and ($pytestCode -eq 0)
    if ($allOk) {
        $verdict = "GO"
    }

    TeardownByPorts -Ports $ports

    $timestamp = Get-Date -Format "yyyyMMdd-HHmm"
    $reportPath = Join-Path $script:ReportsDir "release_gate_proof_${timestamp}.md"
    Write-ProofReport -Path $reportPath -Data @{
        HeadSha = $headSha
        OriginSha = $originSha
        Logs = $logs
        Verdict = $verdict
    }

    Write-Host "`nFinal verdict: $verdict"
    Write-Host "Report: $reportPath"
    if ($verdict -ne "GO") {
        exit 1
    }
}

Main
