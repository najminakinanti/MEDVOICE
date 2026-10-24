# Jalankan MedVoice TANPA Docker: STT + API + worker dari .venv.
# Prasyarat: Postgres (dengan pgvector) dan Redis sudah berjalan; .env memakai host localhost.
#
#   .\run-nodocker.ps1            # start semuanya; Ctrl+C menghentikan
#   .\run-nodocker.ps1 -NoWorker  # tanpa worker (SOAP tidak diproses; cukup untuk uji UI/transkrip langsung)
# UI: http://localhost:8000/ui/   API: http://localhost:8000/v1/docs
param([switch]$NoWorker)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw ".venv tidak ditemukan: $py" }

Get-Content (Join-Path $root ".env") | ForEach-Object {
  if ($_ -match '^\s*([A-Z0-9_]+)=(.*?)\s*(#.*)?$') { Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim() }
}
$env:VOCAB_DIR = Join-Path $root "services\api\config"
# STT di GPU: DLL cuBLAS/cuDNN dari paket pip nvidia-* harus ada di PATH (Windows)
$nv = Join-Path $root ".venv\Lib\site-packages\nvidia"
if (Test-Path $nv) {
  $bins = Get-ChildItem $nv -Directory | ForEach-Object { Join-Path $_.FullName "bin" } | Where-Object { Test-Path $_ }
  if ($bins) { $env:PATH = ($bins -join ";") + ";" + $env:PATH }
}
New-Item -ItemType Directory -Force $env:AUDIO_DIR | Out-Null

# hentikan proses lama yang masih memakai port 8000/9000
foreach ($port in 8000, 9000) {
  Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like "*app.worker.celery*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# cek Redis & Postgres
& $py -c "import redis,os,sys; redis.Redis.from_url(os.environ['REDIS_URL']).ping()" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Redis tidak bisa dihubungi di REDIS_URL. Nyalakan Redis (Laragon) dengan password dari .env." }

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
