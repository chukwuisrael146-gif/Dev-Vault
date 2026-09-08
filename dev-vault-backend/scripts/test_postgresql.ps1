param(
    [string]$PostgresBin = 'C:\Program Files\PostgreSQL\18\bin',
    [int]$Port = 55439,
    [string]$BackupFile = '',
    [switch]$KeepCluster
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$testParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$clusterRoot = [IO.Path]::GetFullPath((Join-Path $testParent ('devvault-pg-test-' + [guid]::NewGuid().ToString('N'))))
if (-not $clusterRoot.StartsWith($testParent, [StringComparison]::OrdinalIgnoreCase) -or
    -not ([IO.Path]::GetFileName($clusterRoot)).StartsWith('devvault-pg-test-')) { throw 'Unsafe test cluster path.' }
$dataPath = Join-Path $clusterRoot 'data'
$logPath = Join-Path $clusterRoot 'postgres.log'
$pythonPath = Join-Path $projectRoot 'venv\Scripts\python.exe'
$pgCtl = Join-Path $PostgresBin 'pg_ctl.exe'
$initDb = Join-Path $PostgresBin 'initdb.exe'
if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $pgCtl)) { throw 'Project Python or PostgreSQL binaries are missing.' }
New-Item -ItemType Directory -Path $clusterRoot | Out-Null
$priorTestUrl = $env:TEST_DATABASE_URL
$priorRedisUrl = $env:DEVVAULT_TEST_REDIS_URL
$priorAccountRedisUrl = $env:TEST_REDIS_URL
$priorBytecode = $env:PYTHONDONTWRITEBYTECODE
$started = $false
$testExit = 1
try {
    & $initDb -D $dataPath -U devvault_test --auth=trust --encoding=UTF8 --no-locale
    if ($LASTEXITCODE -ne 0) { throw 'Disposable PostgreSQL initialization failed.' }
    & $pgCtl -D $dataPath -l $logPath -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) { throw 'Disposable PostgreSQL did not start. Check for a port conflict.' }
    $started = $true
    $env:TEST_DATABASE_URL = "postgresql://devvault_test@127.0.0.1:$Port/postgres"
    $env:DEVVAULT_TEST_REDIS_URL = 'redis://127.0.0.1:6379/15'
    $env:TEST_REDIS_URL = $env:DEVVAULT_TEST_REDIS_URL
    $env:PYTHONDONTWRITEBYTECODE = '1'
    Push-Location $projectRoot
    try {
        if ($BackupFile) {
            $resolvedBackup = (Resolve-Path -LiteralPath $BackupFile).Path
            $backupDirectory = [IO.Path]::GetFullPath((Join-Path $projectRoot 'var\backups')) + [IO.Path]::DirectorySeparatorChar
            if (-not $resolvedBackup.StartsWith($backupDirectory, [StringComparison]::OrdinalIgnoreCase) -or
                [IO.Path]::GetExtension($resolvedBackup) -ne '.dump') { throw 'Only project-local .dump backups may be rehearsed.' }
            & (Join-Path $PostgresBin 'createdb.exe') -h 127.0.0.1 -p $Port -U devvault_test devvault_restore
            if ($LASTEXITCODE -ne 0) { throw 'Restore database creation failed.' }
            & (Join-Path $PostgresBin 'pg_restore.exe') -h 127.0.0.1 -p $Port -U devvault_test --no-owner --no-acl --exit-on-error -d devvault_restore $resolvedBackup
            if ($LASTEXITCODE -ne 0) { throw 'Backup restore failed.' }
            $env:TEST_DATABASE_URL = "postgresql://devvault_test@127.0.0.1:$Port/devvault_restore"
            & $pythonPath -B manage.py migrate --settings=config.settings.postgresql_test_settings --noinput
            if ($LASTEXITCODE -ne 0) { throw 'Restored database migration failed.' }
            & $pythonPath -B manage.py check --settings=config.settings.postgresql_test_settings
            if ($LASTEXITCODE -ne 0) { throw 'Restored database checks failed.' }
            Write-Host 'Private backup restored and upgraded successfully in the disposable cluster.'
            $env:TEST_DATABASE_URL = "postgresql://devvault_test@127.0.0.1:$Port/postgres"
        }
        & $pythonPath -B -m pytest --ds=config.settings.postgresql_test_settings --create-db -q -p no:cacheprovider
        $testExit = $LASTEXITCODE
    } finally { Pop-Location }
} finally {
    if ($started) {
        & $pgCtl -D $dataPath -m fast -w stop
        if ($LASTEXITCODE -ne 0) { throw "Stop failed; test cluster retained at $clusterRoot" }
    }
    $env:TEST_DATABASE_URL = $priorTestUrl
    $env:DEVVAULT_TEST_REDIS_URL = $priorRedisUrl
    $env:TEST_REDIS_URL = $priorAccountRedisUrl
    $env:PYTHONDONTWRITEBYTECODE = $priorBytecode
    if (-not $KeepCluster -and $testExit -eq 0) {
        $resolvedCluster = (Resolve-Path -LiteralPath $clusterRoot).Path
        if ($resolvedCluster -ne $clusterRoot -or -not $resolvedCluster.StartsWith($testParent, [StringComparison]::OrdinalIgnoreCase)) { throw 'Cleanup target validation failed.' }
        Remove-Item -LiteralPath $resolvedCluster -Recurse -Force
        Write-Host 'Disposable test cluster removed. Development databases were not modified.'
    } else { Write-Host "Stopped test cluster retained for inspection: $clusterRoot" }
}
exit $testExit
