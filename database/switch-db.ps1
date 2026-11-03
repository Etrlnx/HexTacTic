<#
.SYNOPSIS
    Switch the active database between the local Docker container and the home server.

.DESCRIPTION
    Reads a DB preset from database/presets/ and splices it into the root .env file,
    replacing only the DB_* and related lines. All other .env vars (CORS_ORIGINS,
    API_KEY, RUNTIME_MODE, etc.) are preserved unchanged.

.PARAMETER Target
    'local'      - use the local Docker Postgres  (database/docker-compose.yml, 127.0.0.1:5433)
    'homeserver' - use the home-server Postgres   (HOMESERVER_DB_HOST:5433)
    If omitted, the script shows a menu.

.EXAMPLE
    .\database\switch-db.ps1 local
    .\database\switch-db.ps1 homeserver
    .\database\switch-db.ps1          # interactive menu
#>
param(
    [ValidateSet("local", "homeserver")]
    [string]$Target = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Resolve paths -------------------------------------------------------------
$repoRoot  = Split-Path -Parent $PSScriptRoot          # database/ -> repo root
$envFile   = Join-Path $repoRoot ".env"
$presetDir = Join-Path $PSScriptRoot "presets"

# -- Interactive menu if no target supplied ------------------------------------
if (-not $Target) {
    Write-Host ""
    Write-Host "  Which database do you want to use?" -ForegroundColor Cyan
    Write-Host "  [1] local       - Docker container on this machine  (127.0.0.1:5433)"
    Write-Host "  [2] homeserver  - Home server Postgres              (HOMESERVER_DB_HOST:5433)"
    Write-Host ""
    $choice = Read-Host "  Enter 1 or 2"
    $Target = switch ($choice) {
        "1" { "local" }
        "2" { "homeserver" }
        default {
            Write-Host "Invalid choice. Exiting." -ForegroundColor Red
            exit 1
        }
    }
}

$presetFile = Join-Path $presetDir "$Target.env"
if (-not (Test-Path $presetFile)) {
    Write-Error "Preset file not found: $presetFile"
    exit 1
}

# -- Load the preset (key=value pairs, skip comments/blanks) ------------------
$presetLines = Get-Content $presetFile
$preset      = [ordered]@{}
foreach ($line in $presetLines) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
    if ($trimmed -match "^([^=]+)=(.*)$") {
        $preset[$matches[1].Trim()] = $matches[2].Trim()
    }
}

# Keys that this script manages (everything in the preset)
$managedKeys = @($preset.Keys)

# -- Read existing .env ---------------------------------------------------------
$existingLines = if (Test-Path $envFile) { Get-Content $envFile } else { @() }

# -- Resolve ${VAR} placeholders from .env so secrets never live in presets ----
$envValues = @{}
foreach ($line in $existingLines) {
    if ($line.Trim() -match "^([^#=][^=]*)=(.*)$" -and -not $envValues.ContainsKey($matches[1].Trim())) {
        $envValues[$matches[1].Trim()] = $matches[2].Trim()
    }
}
foreach ($key in $managedKeys) {
    $value = $preset[$key]
    if ($value -match '^\$\{(\w+)\}$') {
        $var = $matches[1]
        if (-not $envValues.ContainsKey($var) -or $envValues[$var] -eq "") {
            Write-Error "$var is not set in $envFile (needed for $key in the '$Target' preset)."
            exit 1
        }
        $preset[$key] = $envValues[$var]
    }
}

# -- Strip out managed keys -----------------------------------------------------

$kept = [System.Collections.Generic.List[string]]::new()
foreach ($line in $existingLines) {
    $trimmed = $line.Trim()
    # Drop blank/comment lines that are part of a previous DB block header
    $isDbHeader = $trimmed -match "^#.*[Ll]ocal|^#.*[Hh]ome.?server|^#.*[Dd]ocker|^#.*[Pp]ostgres|^#.*(active|unavailable|switch|Other settings)"
    # Drop lines whose key is managed
    $isManagedKey = $false
    if ($trimmed -match "^([^=]+)=") {
        $isManagedKey = $managedKeys -contains $matches[1].Trim()
    }
    if (-not $isManagedKey -and -not $isDbHeader) {
        $kept.Add($line)
    }
}

# -- Build new .env -------------------------------------------------------------
$newLines = [System.Collections.Generic.List[string]]::new()

# Section header
if ($Target -eq "local") {
    $newLines.Add("# -- Local Docker Postgres (database/docker-compose.yml) - ACTIVE --------------")
    $newLines.Add("# Start:  docker compose --env-file .env -f database/docker-compose.yml up -d")
} else {
    $newLines.Add("# -- Home server Postgres (Tailscale / direct IP) - ACTIVE -------------------")
    $newLines.Add("# Make sure the home server and its Docker container are running.")
}

foreach ($key in $managedKeys) {
    $newLines.Add("$key=$($preset[$key])")
}
$newLines.Add("")

# Append remaining (non-DB) lines from the old .env, stripping leading blank lines
$trimmedKept = $kept | Where-Object { $_ -ne "" } | ForEach-Object { $_ }
if ($trimmedKept.Count -gt 0) {
    $newLines.Add("# -- Other settings -----------------------------------------------------------")
    $newLines.AddRange([string[]]$trimmedKept)
}

# -- Write ----------------------------------------------------------------------
Set-Content -Path $envFile -Value $newLines -Encoding UTF8

# -- Summary -------------------------------------------------------------------
Write-Host ""
Write-Host "  [OK]  Switched to: $Target" -ForegroundColor Green
Write-Host "  DB_HOST : $($preset['DB_HOST'])"
Write-Host "  DB_PORT : $($preset['DB_PORT'])"
Write-Host "  DB_NAME : $($preset['DB_NAME'])"
Write-Host "  DB_USER : $($preset['DB_USER'])"
Write-Host ""

if ($Target -eq "local") {
    Write-Host "  Tip: start the container if it isn't running:" -ForegroundColor DarkCyan
    Write-Host "       docker compose --env-file .env -f database/docker-compose.yml up -d" -ForegroundColor DarkCyan
} else {
    Write-Host "  Tip: make sure the home server is online and the Docker container" -ForegroundColor DarkCyan
    Write-Host "       hosting Postgres is running before starting the API." -ForegroundColor DarkCyan
}
Write-Host ""
Write-Host "  Restart the API server for the change to take effect." -ForegroundColor Yellow
Write-Host ""
