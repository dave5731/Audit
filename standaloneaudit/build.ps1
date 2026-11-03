param(
    [string] $PythonExecutable
)

$ErrorActionPreference = 'Stop'

$projectDirectory = $PSScriptRoot
$entryFile = Join-Path $projectDirectory 'standalone_audit.py'
$assetPath = Join-Path $projectDirectory 'assets\nautical-logo.png'
$distDirectory = Join-Path $projectDirectory 'dist'
$buildDirectory = Join-Path $projectDirectory 'build'
$specDirectory = $projectDirectory

if (-not $PythonExecutable) {
    $candidates = @(
        Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python*\python.exe') -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty FullName
    )
    $candidates += (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    $candidates += (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)

    foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        $previousErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        & $candidate -c 'import PyInstaller, playwright' 2>$null
        $candidateExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorPreference
        if ($candidateExitCode -eq 0) {
            $PythonExecutable = $candidate
            break
        }
    }
}

if (-not $PythonExecutable) {
    throw 'Could not find a Python installation containing PyInstaller and Playwright.'
}

& $PythonExecutable -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name standaloneaudit `
    --add-data "$assetPath;assets" `
    --distpath $distDirectory `
    --workpath $buildDirectory `
    --specpath $specDirectory `
    --collect-all playwright `
    $entryFile

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

Write-Output (Join-Path $distDirectory 'standaloneaudit.exe')
