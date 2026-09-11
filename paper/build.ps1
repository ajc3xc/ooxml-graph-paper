# Build script for the preliminary manuscript. Fails loudly on any LaTeX error
# rather than silently leaving a stale or partial PDF in place.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-Checked {
    param([string]$Cmd, [string[]]$CmdArgs)
    & $Cmd @CmdArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "$Cmd $($CmdArgs -join ' ') failed with exit code $LASTEXITCODE"
        exit 1
    }
}

Write-Host "== pdflatex pass 1 =="
Invoke-Checked "pdflatex" @("-interaction=nonstopmode", "-halt-on-error", "main.tex")

Write-Host "== bibtex =="
Invoke-Checked "bibtex" @("main")

Write-Host "== pdflatex pass 2 =="
Invoke-Checked "pdflatex" @("-interaction=nonstopmode", "-halt-on-error", "main.tex")

Write-Host "== pdflatex pass 3 (resolve refs) =="
Invoke-Checked "pdflatex" @("-interaction=nonstopmode", "-halt-on-error", "main.tex")

Write-Host "== preflight =="
python preflight.py

if (Test-Path "main.pdf") {
    Write-Host "Build succeeded: $PSScriptRoot\main.pdf"
} else {
    Write-Error "main.pdf was not produced"
    exit 1
}
