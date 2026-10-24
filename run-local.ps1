# Jalankan MedVoice TANPA membangun image Docker: api + stt + worker langsung dari .venv.
# Hanya infrastruktur (postgres, redis, ollama) yang tetap di Docker (tinggal di-start, tanpa build).
#
#   .\run-local.ps1            # start semuanya (STT, API, worker); Ctrl+C menghentikan
#   .\run-local.ps1 -NoWorker  # tanpa worker (SOAP tidak diproses; cukup untuk uji UI/transkrip langsung)
#   .\run-local.ps1 -Build     # build ulang UI Vue (services/web) dulu
# UI: http://localhost:8000/ui/   Dev UI dengan hot reload: cd services/web; npm run dev  (http://localhost:5173/ui/)
param([switch]$NoWorker, [switch]$Build)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw ".venv tidak ditemukan: $py" }

# .env -> environment, lalu arahkan nama host Docker ke localhost
Get-Content (Join-Path $root ".env") | ForEach-Object {
  if ($_ -match '^\s*([A-Z0-9_]+)=(.*?)\s*(#.*)?$') { Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim() }
}
$pgPort = if ($env:POSTGRES_HOST_PORT) { $env:POSTGRES_HOST_PORT } else { "5432" }
$env:DATABASE_URL = $env:DATABASE_URL -replace '@postgres:5432', "@localhost:$pgPort"
$env:REDIS_URL = $env:REDIS_URL -replace '@redis:6379', '@localhost:6379'
$env:LLM_BASE_URL = "http://localhost:11434"
$env:STT_URL = "http://localhost:9000"
$env:AUDIO_DIR = Join-Path $root ".local\audio"
$env:VOCAB_DIR = Join-Path $root "services\api\config"
New-Item -ItemType Directory -Force $env:AUDIO_DIR | Out-Null

Write-Host "Infrastruktur (Docker): postgres, redis, ollama"
Push-Location $root
$ErrorActionPreference = "Continue"                         # docker menulis progres ke stderr (PS 5.1 menganggapnya galat)
docker compose stop api stt worker *> $null                 # hindari bentrok port 8000/9000 dengan container lama
# LLM memakai GPU NVIDIA (override sama dengan README). Tanpa -f ini container ollama dibuat ulang TANPA GPU (sangat lambat).
$gpu = if (Test-Path "docker-compose.gpu.yml") { @("-f", "docker-compose.yml", "-f", "docker-compose.gpu.yml") } else { @() }
docker compose @gpu up -d --no-build postgres redis ollama *> $null
if ($LASTEXITCODE -ne 0) { throw "docker compose up gagal (pastikan Docker Desktop berjalan)" }
$ErrorActionPreference = "Stop"
Pop-Location

if ($Build) { Push-Location (Join-Path $root "services\web"); npm run build; Pop-Location }

$procs = @()
try {
  $procs += Start-Process $py -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "9000" `
    -WorkingDirectory (Join-Path $root "services\stt") -PassThru -NoNewWindow
  $procs += Start-Process $py -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory (Join-Path $root "services\api") -PassThru -NoNewWindow
  if (-not $NoWorker) {
    $procs += Start-Process $py -ArgumentList "-m", "celery", "-A", "app.worker.celery", "worker", "-P", "solo", "--loglevel=WARNING" `
      -WorkingDirectory (Join-Path $root "services\api") -PassThru -NoNewWindow
  }
  Write-Host "`nBerjalan: UI http://localhost:8000/ui/  |  API /v1/docs  |  STT :9000   (Ctrl+C untuk berhenti)"
  Wait-Process -Id ($procs | ForEach-Object Id)
} finally {
  $procs | ForEach-Object { if (-not $_.HasExited) { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } }
}
