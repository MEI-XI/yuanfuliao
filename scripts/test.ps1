$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = 'utf-8'
$env:TEMP = Join-Path (Get-Location) 'tmp'
$env:TMP = $env:TEMP
if (-not $env:TEST_DATABASE_URL) {
    if (-not (Test-Path 'tmp/test-database-url.txt')) {
        throw 'Set TEST_DATABASE_URL to a dedicated PostgreSQL test database.'
    }
    $env:TEST_DATABASE_URL = (Get-Content 'tmp/test-database-url.txt' -Raw).Trim()
}
& ./.venv/Scripts/python.exe -m pytest @args
exit $LASTEXITCODE
