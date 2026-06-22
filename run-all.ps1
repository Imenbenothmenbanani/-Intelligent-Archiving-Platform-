<#
  run-all.ps1 - One-shot local setup + launch for the Intelligent Archiving Platform (Windows + NVIDIA GPU).

  Usage (from the repo root, in PowerShell):
      ./run-all.ps1                 # full setup + start everything
      ./run-all.ps1 -SetupOnly      # install deps only, don't start services
      ./run-all.ps1 -Cuda cu126     # override the torch CUDA wheel (default: cu128)

  Requirements: Docker Desktop, JDK 21, Maven, Node.js 18+, Python 3.11.
  RTX 50-series (Blackwell) needs the cu128 torch wheels (PyTorch >= 2.7) -> default below.
#>
param(
  [switch]$SetupOnly,
  [string]$Cuda = "cu128"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

Write-Host "==> Repo root: $root" -ForegroundColor Cyan

# 1. .env files (storage -> MinIO, embedder -> OpenSearch)
Write-Host "==> Writing .env files" -ForegroundColor Cyan
@"
CEPH_ACCESS_KEY=minioadmin
CEPH_SECRET_KEY=minioadmin123
CEPH_ENDPOINT=http://localhost:9000
CEPH_REGION=us-east-1
"@ | Set-Content -Encoding ascii "$root\storage_service\config\.env"

@"
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
"@ | Set-Content -Encoding ascii "$root\embendding_service\config\.env"

# 2. OCR service venv (PaddleOCR-VL) - the pipeline launches OCR from ocr_service\.venv
Write-Host "==> Setting up ocr_service venv (this downloads PaddleOCR/Paddle, can be large)" -ForegroundColor Cyan
Push-Location "$root\ocr_service"
if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python -m pip install --upgrade pip poetry
.\.venv\Scripts\poetry config virtualenvs.create false --local
.\.venv\Scripts\poetry install --no-root
Pop-Location

# 3. Pipeline environment (imports storage/chunk/embedding directly)
Write-Host "==> Setting up .venv-pipeline (+ torch $Cuda)" -ForegroundColor Cyan
if (-not (Test-Path "$root\.venv-pipeline")) { python -m venv "$root\.venv-pipeline" }
& "$root\.venv-pipeline\Scripts\python" -m pip install --upgrade pip
& "$root\.venv-pipeline\Scripts\pip" install fastapi uvicorn python-multipart boto3 python-dotenv requests opensearch-py numpy "transformers>=4.40.0"
& "$root\.venv-pipeline\Scripts\pip" install torch --index-url "https://download.pytorch.org/whl/$Cuda"

# 4. Frontend deps
Write-Host "==> npm install (frontend)" -ForegroundColor Cyan
Push-Location "$root\app\frontend-angular"
npm install
Pop-Location

# 5. Backend build
Write-Host "==> Building backend" -ForegroundColor Cyan
Push-Location "$root\app\backend-springboot"
mvn -q -DskipTests package
Pop-Location

if ($SetupOnly) { Write-Host "Setup complete (-SetupOnly). Skipping start." -ForegroundColor Green; exit 0 }

# 6. Start infra
Write-Host "==> Starting MinIO + OpenSearch (docker compose)" -ForegroundColor Cyan
docker compose up -d
Write-Host "    Waiting 20s for OpenSearch to come up..." -ForegroundColor DarkGray
Start-Sleep -Seconds 20

# 7. Start services, each in its own window
function Start-In-Window($title, $command) {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle='$title'; cd '$root'; $command"
}

Start-In-Window "Pipeline :8082" ".\.venv-pipeline\Scripts\python app\pipeline_service\main.py"
Start-Sleep -Seconds 3
Start-In-Window "Backend :8081"  "cd app\backend-springboot; java -jar target\backend-springboot-0.0.1-SNAPSHOT.jar"
Start-In-Window "Frontend :4200" "cd app\frontend-angular; npm start"

Write-Host ""
Write-Host "All started. Open http://localhost:4200" -ForegroundColor Green
Write-Host "  Pipeline health: http://localhost:8082/health"
Write-Host "  Backend health:  http://localhost:8081/api/documents/health"
Write-Host "  MinIO console:   http://localhost:9001 (minioadmin / minioadmin123)"
Write-Host "  Make sure your scanner agent is running on http://127.0.0.1:7777"
