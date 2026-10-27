$ErrorActionPreference = "Stop"

$projectDir = "C:\Users\supri\Desktop\BDA\server-log-anomaly-detection"
Set-Location $projectDir

Write-Host "Checking Docker..."
while ($true) {
    try {
        docker info | Out-Null
        Write-Host "Docker ready"
        break
    }
    catch {
        Write-Host "Docker not ready yet. Waiting 10 seconds..."
        Start-Sleep -Seconds 10
    }
}

Write-Host "Starting stack..."
docker compose up -d

Write-Host "Waiting for services..."
for ($i = 0; $i -lt 30; $i++) {
    try {
        $ps = docker compose ps
        if ($ps -match "healthy") {
            Write-Host "Services healthy enough to continue."
            break
        }
    }
    catch {
        Write-Host "Compose not ready yet..."
    }
    Start-Sleep -Seconds 10
}

Write-Host "Creating topics..."
make topics

Write-Host "Applying index templates..."
make apply-index-templates

Write-Host "Startup complete."