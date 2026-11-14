Param(
  [string]$OutZip = "blind-assist-review.zip",
  [switch]$ExcludeEnv
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root

try {
  $exclude = @(
    "vision_ai_env",
    "__pycache__",
    "alerts",
    "temp.jpg"
  )
  if ($ExcludeEnv) { $exclude += ".env" }

  $items = Get-ChildItem -Force | Where-Object { $exclude -notcontains $_.Name } | Select-Object -ExpandProperty Name
  if (Test-Path $OutZip) { Remove-Item -Force $OutZip }

  Compress-Archive -Path $items -DestinationPath $OutZip -Force
  Write-Host "Created: $OutZip"
  Write-Host "Excluded: $($exclude -join ', ')"
} finally {
  Pop-Location
}
