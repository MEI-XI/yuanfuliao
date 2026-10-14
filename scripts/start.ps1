param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = 'utf-8'
$env:TEMP = Join-Path (Get-Location) 'tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force tmp | Out-Null
if (-not (Test-Path '.env')) { throw '请先根据 .env.example 建立 .env 并配置 PostgreSQL。' }
if (-not (Test-Path 'frontend/dist/index.html')) { throw '请先在 frontend 目录执行 npm ci 和 npm run build。' }
# This local portable database belongs only to this project. Existing company
# PostgreSQL installations are selected through DATABASE_URL instead.
if ((Test-Path 'tmp/pg-runtime/pgsql/bin/pg_ctl.exe') -and (Test-Path 'data/postgres-local/PG_VERSION')) {
    & ./tmp/pg-runtime/pgsql/bin/pg_ctl.exe -D data/postgres-local status *> $null
    if ($LASTEXITCODE -ne 0) {
        Start-Process -FilePath (Resolve-Path 'tmp/pg-runtime/pgsql/bin/postgres.exe') -ArgumentList @('-D', (Join-Path (Get-Location) 'data/postgres-local'), '-h', '127.0.0.1', '-p', '55433') -WindowStyle Hidden -RedirectStandardOutput (Join-Path (Get-Location) 'tmp/postgres-local.log') -RedirectStandardError (Join-Path (Get-Location) 'tmp/postgres-local-error.log')
        for ($attempt = 0; $attempt -lt 15; $attempt++) {
            & ./tmp/pg-runtime/pgsql/bin/pg_isready.exe -h 127.0.0.1 -p 55433 -t 1 *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 1
        }
        if ($LASTEXITCODE -ne 0) { throw '项目数据库尚未就绪，请查看 tmp/postgres-local-error.log。' }
    }
}
Write-Host "本机访问：http://127.0.0.1:$Port；手机在同一局域网使用本机局域网IP和此端口。按 Ctrl+C 停止网页服务。"
& ./.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port $Port
exit $LASTEXITCODE
