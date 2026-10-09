# Starts Ollama and the Pocket Walk page.  Usage:  .\start.ps1        (this computer only)
#                                                  .\start.ps1 -Lan   (also reachable from your phone)
param([switch]$Lan)

$ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"

# Ollama's CUDA build needs a recent NVIDIA driver. On older drivers it crashes, so run the
# model through Vulkan instead, which works on the same card. Remove these two lines once
# your driver is up to date.
$env:OLLAMA_VULKAN = "1"
$env:CUDA_VISIBLE_DEVICES = "-1"

Get-Process | Where-Object { $_.Name -like "ollama*" } | Stop-Process -Force -Confirm:$false
Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden
Start-Sleep 3

$serveArgs = @("-m", "pocketwalk", "serve")
if ($Lan) { $serveArgs += "--lan" }
& "$PSScriptRoot\.venv\Scripts\python.exe" @serveArgs
