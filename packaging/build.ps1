<#
.SYNOPSIS
    Construye el ejecutable de Windows de gee-recipe-builder.

.DESCRIPTION
    Genera dist\gee-recipe-builder\gee-recipe-builder.exe (modo onedir),
    corre el smoke test contra el binario ya congelado y, con -Zip, empaqueta
    la carpeta lista para distribuir.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Console -Zip
#>
[CmdletBinding()]
param(
    # Construye la variante con consola: muestra tracebacks si el .exe muere sin decir nada.
    [switch]$Console,
    # Comprime dist\gee-recipe-builder\ en dist\gee-recipe-builder-win64.zip.
    [switch]$Zip,
    # Salta el smoke test post-build.
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller no está instalado. Instalando..." -ForegroundColor Yellow
    python -m pip install "pyinstaller>=6.10"
    if ($LASTEXITCODE -ne 0) { throw "no se pudo instalar PyInstaller" }
}

if ($Console) { $env:GRB_CONSOLE = "1" } else { Remove-Item Env:\GRB_CONSOLE -ErrorAction SilentlyContinue }

Write-Host "Construyendo (esto tarda 2-4 min)..." -ForegroundColor Cyan
python -m PyInstaller "packaging\gee-recipe-builder.spec" --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "el build falló" }

$exe = Join-Path $raiz "dist\gee-recipe-builder\gee-recipe-builder.exe"
if (-not (Test-Path $exe)) { throw "no se generó $exe" }

if (-not $SkipSmoke) {
    Write-Host "Corriendo smoke test contra el binario..." -ForegroundColor Cyan
    $p = Start-Process -FilePath $exe -ArgumentList "--smoke" -Wait -PassThru
    $log = Join-Path (Split-Path $exe) "grb-smoke.log"
    if (Test-Path $log) { Get-Content $log }
    if ($p.ExitCode -ne 0) { throw "el smoke test falló (exit $($p.ExitCode)) — ver $log" }
}

if ($Zip) {
    $zip = Join-Path $raiz "dist\gee-recipe-builder-win64.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Write-Host "Comprimiendo..." -ForegroundColor Cyan
    Compress-Archive -Path (Join-Path $raiz "dist\gee-recipe-builder\*") -DestinationPath $zip
    Write-Host "Zip: $zip" -ForegroundColor Green
}

$mb = [math]::Round(((Get-ChildItem (Split-Path $exe) -Recurse | Measure-Object Length -Sum).Sum / 1MB))
Write-Host "Listo: $exe ($mb MB con dependencias)" -ForegroundColor Green
