<#
.SYNOPSIS
  Makes a LOCAL COPY of your Supabase database so the app responds instantly while you develop.

.DESCRIPTION
  * Only READS from Supabase (pg_dump). Nothing in Supabase is changed.
  * Creates a separate local container "farm-local-pg" on port 5433 with its own volume; it does not touch the
    database from docker-compose.yml (port 5432).
  * Uses the same Postgres major version as your Supabase project, so the dump always restores.
  * Does NOT edit apps/api/.env unless you pass -SwitchEnv (it then keeps a backup, .env.bak).
  * The copy is a snapshot: changes you make locally are not sent to Supabase.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\local_db_copy.ps1
  powershell -ExecutionPolicy Bypass -File scripts\local_db_copy.ps1 -SwitchEnv
#>
param(
    [string]$EnvFile   = "apps/api/.env",
    [string]$SourceUrl = "",          # optional: postgresql://user:password@host:5432/postgres
    [int]$Port         = 5433,
    [switch]$Recreate,                # delete an existing local copy and make a fresh one
    [switch]$SwitchEnv                # point apps/api/.env at the local copy afterwards
)
$ErrorActionPreference = "Stop"
$Container = "farm-local-pg"
$Volume    = "farm_local_pgdata"
$Dump      = "farm_backup.dump"

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

# ---- 0. Docker must be running
Step "Checking Docker"
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop and run this again." }

# ---- 1. Where to copy from
if (-not $SourceUrl) {
    if (-not (Test-Path $EnvFile)) { throw "Cannot find $EnvFile. Run from the project root or pass -SourceUrl." }
    $line = Get-Content $EnvFile | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
    if (-not $line) { throw "No active DATABASE_URL line in $EnvFile (is it commented out?). Pass -SourceUrl instead." }
    $SourceUrl = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
}
$SourceUrl = $SourceUrl -replace '^postgresql\+\w+://', 'postgresql://'
if ($SourceUrl -match '@(localhost|127\.0\.0\.1)') { throw "DATABASE_URL already points at a local database; nothing to copy." }

# ---- 2. Match the server's Postgres version
Step "Checking the Supabase Postgres version (read-only)"
$verNum = "$(docker run --rm postgres:17-alpine psql $SourceUrl -tAc "show server_version_num")".Trim()
if ($LASTEXITCODE -ne 0 -or -not $verNum) { throw "Could not connect to the source database. Check the URL/password and your internet." }
$major = [int]$verNum.Substring(0, 2)
Write-Host "Server is Postgres $major"

# ---- 3. Dump (public schema only; the app lives there)
Step "Dumping the database (this can take a few minutes over the internet)"
docker run --rm -v "${PWD}:/dump" "postgres:$major-alpine" pg_dump $SourceUrl --no-owner --no-privileges --schema=public --format=custom --file="/dump/$Dump"
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }
Write-Host ("Saved {0} ({1:N1} MB)" -f $Dump, ((Get-Item $Dump).Length / 1MB))

# ---- 4. Local container
Step "Preparing the local database container"
$exists = docker ps -a --filter "name=^/$Container$" --format "{{.Names}}"
if ($exists) {
    if (-not $Recreate) { throw "Container $Container already exists. Re-run with -Recreate to replace it (its data will be lost)." }
    docker rm -f $Container | Out-Null
    docker volume rm $Volume 2>$null | Out-Null
}
docker run -d --name $Container -e POSTGRES_USER=farm -e POSTGRES_PASSWORD=farm -e POSTGRES_DB=farmdb `
    -p "${Port}:5432" -v "${Volume}:/var/lib/postgresql/data" "postgres:$major-alpine" | Out-Null
for ($i = 0; $i -lt 40; $i++) {
    docker exec $Container pg_isready -U farm -d farmdb *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
}
if ($LASTEXITCODE -ne 0) { throw "The local database did not start." }

# ---- 5. Restore
Step "Restoring into the local database"
docker cp $Dump "${Container}:/tmp/$Dump" | Out-Null
docker exec $Container pg_restore -U farm -d farmdb --no-owner --no-privileges "/tmp/$Dump"
if ($LASTEXITCODE -ne 0) { Write-Host "pg_restore reported warnings (usually harmless: missing Supabase-only roles/extensions). Check the counts below." -ForegroundColor Yellow }

# ---- 6. Verify against the source
Step "Comparing row counts (Supabase vs local)"
foreach ($t in @("organizations", "animals", "intake_batches", "feedlot_animals", "weight_records", "finance_transactions")) {
    $src = "$(docker run --rm "postgres:$major-alpine" psql $SourceUrl -tAc "select count(*) from $t" 2>$null)".Trim()
    $loc = "$(docker exec $Container psql -U farm -d farmdb -tAc "select count(*) from $t" 2>$null)".Trim()
    $ok  = if ($src -and $src -eq $loc) { "OK" } else { "CHECK" }
    "{0,-22} supabase={1,-8} local={2,-8} {3}" -f $t, $src, $loc, $ok
}

$LocalUrl = "postgresql+psycopg://farm:farm@localhost:${Port}/farmdb"
if ($SwitchEnv) {
    Step "Pointing $EnvFile at the local copy (backup: $EnvFile.bak)"
    Copy-Item $EnvFile "$EnvFile.bak" -Force
    $out = foreach ($l in Get-Content $EnvFile) {
        if ($l -match '^\s*DATABASE_URL\s*=') { "# (was Supabase) $l"; "DATABASE_URL=$LocalUrl" } else { $l }
    }
    Set-Content -Path $EnvFile -Value $out
} else {
    Write-Host "`nTo use it, in $EnvFile comment out the Supabase DATABASE_URL and add:" -ForegroundColor Green
    Write-Host "DATABASE_URL=$LocalUrl"
}
Write-Host "`nNext: cd apps\api ; alembic upgrade head ; restart the API." -ForegroundColor Green
Write-Host "To go back to Supabase: restore the DATABASE_URL line (or copy $EnvFile.bak back)."