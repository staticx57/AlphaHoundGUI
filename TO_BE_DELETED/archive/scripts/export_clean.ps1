$source = Get-Location
$dest = "$source\N42_Viewer_Clean"

Write-Host "Exporting clean source code to: $dest"

# Create dest
New-Item -ItemType Directory -Force -Path $dest | Out-Null
New-Item -ItemType Directory -Force -Path "$dest\backend" | Out-Null
New-Item -ItemType Directory -Force -Path "$dest\backend\static" | Out-Null

# Copy Root Files
Copy-Item "README.md" -Destination $dest
Copy-Item "TODO.md" -Destination $dest
Copy-Item "CHANGELOG.md" -Destination $dest
Copy-Item "advanced_features_plan.md" -Destination $dest
Copy-Item ".gitignore" -Destination $dest
Copy-Item "launch.bat" -Destination $dest
Copy-Item "setup_env.bat" -Destination $dest

# Copy Backend Files (White-list approach to avoid venv/logs)
Get-ChildItem "backend\*.py" | Copy-Item -Destination "$dest\backend"
Get-ChildItem "backend\requirements.txt" | Copy-Item -Destination "$dest\backend"

# Copy Static Files
Copy-Item "backend\static\*" -Destination "$dest\backend\static" -Recurse

Write-Host "Done! You can now move '$dest' to your git folder."
