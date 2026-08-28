<#
.SYNOPSIS
    Corre la suite deterministica: tests base + tests de regresion generados por el agente.

.DESCRIPTION
    Cierra el ciclo hibrido. El agente explora y genera tests en
    out/run-*/regression/. Este script los junta con los tests base y los corre
    todos con Pester, sin IA y sin costo.

.EXAMPLE
    .\tests\Invoke-Regression.ps1
    .\tests\Invoke-Regression.ps1 -Tag negocio -CI
    .\tests\Invoke-Regression.ps1 -RunDir ..\out\run-20260821-101500
#>
[CmdletBinding()]
param(
    [string]$RunDir,
    [string[]]$Tag,
    [switch]$CI,
    [switch]$IncludeGenerated = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Module -ListAvailable -Name Pester |
          Where-Object { $_.Version.Major -ge 5 })) {
    throw 'Se requiere Pester 5+. Instalar con: Install-Module Pester -Force -SkipPublisherCheck'
}
Import-Module Pester -MinimumVersion 5.0 -Force

$root  = Split-Path $PSScriptRoot -Parent
$paths = @($PSScriptRoot)

if ($IncludeGenerated) {
    if ($RunDir) {
        $genDir = Join-Path $RunDir 'regression'
    }
    else {
        $latest = Join-Path $root 'out\latest.txt'
        $genDir = if (Test-Path $latest) {
            Join-Path (Get-Content $latest -Raw).Trim() 'regression'
        } else { $null }
    }

    if ($genDir -and (Test-Path $genDir)) {
        $count = @(Get-ChildItem -Path $genDir -Filter '*.Tests.ps1').Count
        Write-Host "Incluyendo $count tests de regresion generados desde $genDir" -ForegroundColor Cyan
        $paths += $genDir
    }
    else {
        Write-Host 'Sin tests de regresion generados todavia.' -ForegroundColor DarkGray
    }
}

$cfg = New-PesterConfiguration
$cfg.Run.Path        = $paths
$cfg.Output.Verbosity = 'Detailed'

if ($Tag) { $cfg.Filter.Tag = $Tag }

if ($CI) {
    $cfg.TestResult.Enabled      = $true
    $cfg.TestResult.OutputFormat = 'NUnitXml'
    $cfg.TestResult.OutputPath   = Join-Path $root 'out\pester-results.xml'
    $cfg.Run.Exit                = $true
}

Invoke-Pester -Configuration $cfg
