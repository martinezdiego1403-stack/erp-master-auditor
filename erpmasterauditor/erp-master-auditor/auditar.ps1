# Lanza el auditor contra Abasto ERP con el entorno ya preparado.
#
#   .\auditar.ps1 doctor              verificar conexion (gratis)
#   .\auditar.ps1 doctor --web        ademas abrir la interfaz y sacar captura
#   .\auditar.ps1 mission 00          correr una mision
#   .\auditar.ps1 mission 11          auditar la interfaz web
#   .\auditar.ps1 full                auditoria completa (respeta max_cost_usd)
#
# Antes de correrlo tienen que estar levantados la API (:5180) y el
# frontend (:5173) del ERP:  AbastoERP\tools\dev.ps1
param([Parameter(ValueFromRemainingArguments)][string[]]$Args)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

# Credenciales: si no estan en el entorno, se piden una vez.
if (-not $env:ABASTO_EMAIL) { $env:ABASTO_EMAIL = Read-Host 'Email del ERP' }
if (-not $env:ABASTO_PASSWORD) {
    $s = Read-Host 'Contrasena del ERP' -AsSecureString
    $env:ABASTO_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}
if (-not $env:ABASTO_AUDITOR_PASSWORD) { $env:ABASTO_AUDITOR_PASSWORD = 'auditor2026' }
if (-not $env:PG_PASSWORD) {
    $s = Read-Host 'Contrasena de PostgreSQL' -AsSecureString
    $env:PG_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}

# El ERP tiene que estar arriba: si no, el agente gasta una mision para nada.
foreach ($u in @('http://localhost:5180/openapi/v1.json', 'http://localhost:5173')) {
    try { Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 5 | Out-Null }
    catch { throw "No responde $u. Levanta el ERP con AbastoERP\tools\dev.ps1 antes de auditar." }
}

& .\.venv\Scripts\python.exe -m auditor.run @Args
