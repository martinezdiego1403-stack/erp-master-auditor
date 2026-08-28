<#
.SYNOPSIS
    Driver de consola del ERP para tests Pester.

.DESCRIPTION
    La mitad deterministica del auditor hibrido. El agente explora y descubre;
    lo que descubre se congela aca como test que corre en cada commit, sin IA,
    sin costo y sin variabilidad.

    Maneja el ERP como proceso hijo con stdin/stdout redirigidos y lee con la
    misma heuristica de "quiet period" que usa el agente: se lee hasta que
    pasan N ms sin bytes nuevos o aparece el prompt esperado.

.NOTES
    Requiere Pester 5+.   Install-Module Pester -Force -SkipPublisherCheck
#>

Set-StrictMode -Version Latest

function Get-ErpTestConfig {
    <#
    .SYNOPSIS
        Lee tests/erp.test.config.json (espejo de config.yaml).
    #>
    [CmdletBinding()]
    param([string]$Path)

    if (-not $Path) {
        $Path = Join-Path $PSScriptRoot 'erp.test.config.json'
    }
    if (-not (Test-Path $Path)) {
        throw "No existe $Path. Genera el archivo con: python -m auditor.run export-pester-config"
    }
    $cfg = Get-Content -Path $Path -Raw -Encoding UTF8 | ConvertFrom-Json

    foreach ($required in @('Command', 'Arguments')) {
        if ($cfg.PSObject.Properties.Name -notcontains $required) {
            throw "erp.test.config.json: falta la propiedad '$required'"
        }
    }
    return $cfg
}

function Test-ErpConfigProperty {
    param($Config, [string]$Name)
    return ($Config.PSObject.Properties.Name -contains $Name) -and $null -ne $Config.$Name
}

function Start-ErpSession {
    <#
    .SYNOPSIS
        Arranca el ERP y devuelve un objeto de sesion.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Config,
        [string]$TranscriptPath
    )

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName               = $Config.Command
    $psi.UseShellExecute         = $false
    $psi.RedirectStandardInput   = $true
    $psi.RedirectStandardOutput  = $true
    $psi.RedirectStandardError   = $true
    $psi.CreateNoWindow          = $true

    # ArgumentList existe en .NET Core / PowerShell 7. En Windows PowerShell 5.1
    # hay que armar la linea de comando a mano.
    if ($psi.PSObject.Properties.Name -contains 'ArgumentList') {
        foreach ($a in $Config.Arguments) { [void]$psi.ArgumentList.Add([string]$a) }
    }
    else {
        $psi.Arguments = (
            $Config.Arguments | ForEach-Object {
                if ("$_" -match '\s') { '"' + "$_" + '"' } else { "$_" }
            }
        ) -join ' '
    }

    if (Test-ErpConfigProperty $Config 'WorkingDirectory') {
        $psi.WorkingDirectory = $Config.WorkingDirectory
    }

    $encodingName = 'utf-8'
    if (Test-ErpConfigProperty $Config 'Encoding') { $encodingName = $Config.Encoding }

    # Importante: [Text.Encoding]::GetEncoding('utf-8') emite BOM, y el BOM viaja
    # como primeros bytes de stdin. El ERP recibe "﻿1" en vez de "1" y responde
    # "opcion invalida". Hay que usar UTF8 sin BOM.
    $encoding = if ($encodingName -replace '-', '' -ieq 'utf8') {
        [System.Text.UTF8Encoding]::new($false)
    } else {
        [System.Text.Encoding]::GetEncoding($encodingName)
    }
    $psi.StandardOutputEncoding = $encoding
    $psi.StandardErrorEncoding  = $encoding
    if ($psi.PSObject.Properties.Name -contains 'StandardInputEncoding') {
        $psi.StandardInputEncoding = $encoding
    }

    if (Test-ErpConfigProperty $Config 'Environment') {
        foreach ($kv in $Config.Environment.PSObject.Properties) {
            $psi.Environment[$kv.Name] = [string]$kv.Value
        }
    }

    $proc = [System.Diagnostics.Process]::Start($psi)

    [pscustomobject]@{
        Process        = $proc
        Stream         = $proc.StandardOutput.BaseStream
        Decoder        = $encoding.GetDecoder()
        Buffer         = [byte[]]::new(8192)
        PendingRead    = $null
        QuietMs        = if (Test-ErpConfigProperty $Config 'QuietMs')      { $Config.QuietMs }   else { 400 }
        MaxWaitMs      = if (Test-ErpConfigProperty $Config 'MaxWaitMs')    { $Config.MaxWaitMs } else { 8000 }
        ReadyPattern   = if (Test-ErpConfigProperty $Config 'ReadyPattern') { $Config.ReadyPattern } else { $null }
        TranscriptPath = $TranscriptPath
    }
}

function Read-ErpOutput {
    <#
    .SYNOPSIS
        Lee la salida del ERP hasta el quiet period, el prompt esperado o el techo de espera.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Session,
        [int]$QuietMs,
        [int]$MaxWaitMs,
        [string]$Until
    )

    if (-not $QuietMs)   { $QuietMs   = $Session.QuietMs }
    if (-not $MaxWaitMs) { $MaxWaitMs = $Session.MaxWaitMs }
    if (-not $Until)     { $Until     = $Session.ReadyPattern }

    $sb       = [System.Text.StringBuilder]::new()
    $deadline = [datetime]::UtcNow.AddMilliseconds($MaxWaitMs)
    $lastData = $null

    while ($true) {
        if ($null -eq $Session.PendingRead) {
            $Session.PendingRead = $Session.Stream.ReadAsync($Session.Buffer, 0, $Session.Buffer.Length)
        }

        if ($Session.PendingRead.Wait(50)) {
            $n = $Session.PendingRead.Result
            $Session.PendingRead = $null
            if ($n -le 0) { break }   # EOF: el proceso cerro stdout
            $chars = [char[]]::new($n * 2)
            $c = $Session.Decoder.GetChars($Session.Buffer, 0, $n, $chars, 0)
            [void]$sb.Append($chars, 0, $c)
            $lastData = [datetime]::UtcNow
        }

        $text = $sb.ToString()
        if ($Until -and $text -match $Until) { break }
        if ($lastData -and ([datetime]::UtcNow - $lastData).TotalMilliseconds -ge $QuietMs) { break }
        if ([datetime]::UtcNow -ge $deadline) { break }
    }

    $out = $sb.ToString()
    if ($Session.TranscriptPath) {
        Add-Content -Path $Session.TranscriptPath -Value "`n--- OUT ---`n$out" -Encoding UTF8
    }
    return $out
}

function Send-ErpInput {
    <#
    .SYNOPSIS
        Escribe una linea en la consola del ERP y devuelve lo que responde.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Session,
        [Parameter(Mandatory)] [AllowEmptyString()] [string]$Text,
        [int]$MaxWaitMs
    )

    if ($Session.Process.HasExited) {
        throw "El ERP ya no esta corriendo (exit code $($Session.Process.ExitCode)) al intentar enviar '$Text'"
    }
    if ($Session.TranscriptPath) {
        Add-Content -Path $Session.TranscriptPath -Value "`n--- IN --- $Text" -Encoding UTF8
    }

    $Session.Process.StandardInput.WriteLine($Text)
    $Session.Process.StandardInput.Flush()

    Read-ErpOutput -Session $Session -MaxWaitMs $MaxWaitMs
}

function Stop-ErpSession {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Session)

    try {
        if (-not $Session.Process.HasExited) {
            $Session.Process.Kill()
            [void]$Session.Process.WaitForExit(5000)
        }
    } catch { }
    finally {
        try { $Session.Process.Dispose() } catch { }
    }
}

function Reset-ErpTestData {
    <#
    .SYNOPSIS
        Deja la base en estado conocido antes de un test.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config)

    if (-not (Test-ErpConfigProperty $Config 'ResetCommand')) {
        Write-Verbose 'ResetCommand no configurado; se omite el reset.'
        return
    }
    $resetArgs = @()
    if (Test-ErpConfigProperty $Config 'ResetArguments') {
        $resetArgs = $Config.ResetArguments
    }
    & $Config.ResetCommand @resetArgs | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "El reset de datos fallo con codigo $LASTEXITCODE"
    }
}

function Invoke-ErpFlow {
    <#
    .SYNOPSIS
        Atajo: arranca, envia una secuencia de inputs, devuelve la salida final y cierra.
    .EXAMPLE
        $out = Invoke-ErpFlow -Config $cfg -Inputs @('2','1','CLI001','PROD-100','5','S')
        $out | Should -Match 'Pedido .* registrado'
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Config,
        [Parameter(Mandatory)] [string[]]$Inputs,
        [switch]$Reset,
        [string]$TranscriptPath
    )

    if ($Reset) { Reset-ErpTestData -Config $Config }

    $s = Start-ErpSession -Config $Config -TranscriptPath $TranscriptPath
    try {
        $out = Read-ErpOutput -Session $s
        foreach ($i in $Inputs) {
            $out = Send-ErpInput -Session $s -Text $i
        }
        return $out
    }
    finally {
        Stop-ErpSession -Session $s
    }
}

Export-ModuleMember -Function @(
    'Get-ErpTestConfig',
    'Test-ErpConfigProperty',
    'Start-ErpSession',
    'Read-ErpOutput',
    'Send-ErpInput',
    'Stop-ErpSession',
    'Reset-ErpTestData',
    'Invoke-ErpFlow'
)
