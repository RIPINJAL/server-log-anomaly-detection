$ErrorActionPreference = 'Stop'

$envPath = Join-Path $PSScriptRoot '..\.env'
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^[^#\s][^=]*=') {
            $parts = $_ -split '=', 2
            $name = $parts[0].Trim()
            $value = $parts[1].Trim()
            if ($name) {
                [Environment]::SetEnvironmentVariable($name, $value, 'Process')
            }
        }
    }
}

$esHost = if ($env:ELASTICSEARCH_EXTERNAL_HOST) { $env:ELASTICSEARCH_EXTERNAL_HOST } else { 'localhost' }
$esPort = if ($env:ELASTICSEARCH_PORT) { $env:ELASTICSEARCH_PORT } else { '9200' }
$esUrl = "http://${esHost}:${esPort}"
$serverTemplate = Get-Content (Join-Path $PSScriptRoot '../elastic_config/index_templates/server-logs-template.json') -Raw
$anomalyTemplate = Get-Content (Join-Path $PSScriptRoot '../elastic_config/index_templates/anomalies-template.json') -Raw

Invoke-RestMethod -Method Put -Uri "$esUrl/_index_template/server-logs-template" -ContentType 'application/json' -Body $serverTemplate -UseBasicParsing | Out-Null
Invoke-RestMethod -Method Put -Uri "$esUrl/_index_template/anomalies-template" -ContentType 'application/json' -Body $anomalyTemplate -UseBasicParsing | Out-Null
Write-Host "Applied index templates"
