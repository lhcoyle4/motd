# install.ps1 - Installer for Terminal MOTD
# Can be run normally to install, or with -Uninstall to remove.

param (
    [switch]$Uninstall
)

$scriptPath = "$PSScriptRoot\main.py"
$absoluteScriptPath = [System.IO.Path]::GetFullPath($scriptPath)

# Define profile paths
# CurrentUserCurrentHost for Windows PowerShell and PowerShell 7+
$profiles = @(
    "$env:USERPROFILE\OneDrive\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1",
    "$env:USERPROFILE\OneDrive\Documents\PowerShell\Microsoft.PowerShell_profile.ps1",
    "$env:USERPROFILE\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1",
    "$env:USERPROFILE\Documents\PowerShell\Microsoft.PowerShell_profile.ps1"
)

# Dedup profile paths
$profiles = $profiles | Select-Object -Unique

# Hook markers
$beginMarker = "# BEGIN TERMINAL MOTD HOOK"
$endMarker = "# END TERMINAL MOTD HOOK"
$hookCode = @"
$beginMarker
if (Test-Path "$absoluteScriptPath") {
    python "$absoluteScriptPath"
}
$endMarker
"@

function Remove-Hook {
    param ($profilePath)
    if (Test-Path $profilePath) {
        $content = Get-Content $profilePath -Raw
        # Regex to remove everything between markers inclusive
        $pattern = "(?s)\s*" + [regex]::Escape($beginMarker) + ".*?" + [regex]::Escape($endMarker) + "\s*"
        if ($content -match $pattern) {
            $newContent = $content -replace $pattern, "`r`n"
            $newContent = $newContent.Trim()
            if ($newContent -eq "") {
                Remove-Item $profilePath -Force
                Write-Host "Removed empty profile: $profilePath"
            } else {
                Set-Content $profilePath $newContent -Force
                Write-Host "Removed MOTD hook from profile: $profilePath"
            }
        }
    }
}

function Add-Hook {
    param ($profilePath)
    # Remove existing first to prevent duplication
    Remove-Hook $profilePath
    
    # Create directory if it doesn't exist
    $dir = Split-Path $profilePath -Parent
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    
    # Create profile file if it doesn't exist
    if (!(Test-Path $profilePath)) {
        New-Item -ItemType File -Path $profilePath -Force | Out-Null
    }
    
    # Append hook code
    $content = Get-Content $profilePath -Raw
    if ($content -and !$content.EndsWith("`n")) {
        $hookCode = "`r`n`r`n" + $hookCode
    } else {
        $hookCode = "`r`n" + $hookCode
    }
    
    Add-Content $profilePath $hookCode -Force
    Write-Host "Installed MOTD hook to profile: $profilePath"
}

if ($Uninstall) {
    Write-Host "Uninstalling Terminal MOTD hook..." -ForegroundColor Yellow
    foreach ($profile in $profiles) {
        Remove-Hook $profile
    }
    Write-Host "Terminal MOTD hook successfully uninstalled!" -ForegroundColor Green
} else {
    Write-Host "Installing Terminal MOTD hook..." -ForegroundColor Cyan
    Write-Host "Target script: $absoluteScriptPath"
    
    # Verify script exists
    if (!(Test-Path $absoluteScriptPath)) {
        Write-Error "main.py not found at $absoluteScriptPath. Please make sure main.py is in the same directory as this script."
        exit 1
    }
    
    foreach ($profile in $profiles) {
        Add-Hook $profile
    }
    Write-Host "Terminal MOTD hook successfully installed!" -ForegroundColor Green
    Write-Host "Open a new PowerShell terminal to see it in action!" -ForegroundColor Green
}
