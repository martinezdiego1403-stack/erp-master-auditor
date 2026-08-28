<#
    Tests base de humo. Ajusta los patrones a lo que imprime TU ERP.
    Estos tres tests son el piso: si fallan, el arnes no esta bien conectado
    y no tiene sentido correr al agente todavia.

    Ejecutar:  Invoke-Pester -Path .\tests -Output Detailed
#>

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot 'ERPConsole.psm1') -Force
    $script:Cfg = Get-ErpTestConfig
}

Describe 'Arnes de consola' -Tag 'smoke' {

    It 'el ERP arranca y muestra una pantalla inicial' {
        $s = Start-ErpSession -Config $script:Cfg
        try {
            $out = Read-ErpOutput -Session $s
            $out | Should -Not -BeNullOrEmpty
            # AJUSTAR: algo que tu ERP siempre imprime al arrancar
            $out | Should -Match 'MENU|Menu|Opcion|ERP'
        }
        finally { Stop-ErpSession -Session $s }
    }

    It 'responde a un input y sigue vivo' {
        $s = Start-ErpSession -Config $script:Cfg
        try {
            [void](Read-ErpOutput -Session $s)
            $out = Send-ErpInput -Session $s -Text '1'   # AJUSTAR
            $out | Should -Not -BeNullOrEmpty
            $s.Process.HasExited | Should -BeFalse
        }
        finally { Stop-ErpSession -Session $s }
    }

    It 'no muestra excepciones sin manejar ante un input invalido' {
        $s = Start-ErpSession -Config $script:Cfg
        try {
            [void](Read-ErpOutput -Session $s)
            $out = Send-ErpInput -Session $s -Text 'zzz-input-invalido-999'
            $out | Should -Not -Match 'Unhandled exception|System\.\w+Exception|at [A-Z]\w+\.'
            $s.Process.HasExited | Should -BeFalse
        }
        finally { Stop-ErpSession -Session $s }
    }
}

Describe 'Reglas de negocio criticas' -Tag 'negocio' {

    It 'no permite vender mas stock del disponible' -Skip {
        # PLANTILLA. Quitar -Skip y ajustar la secuencia a tu ERP.
        $out = Invoke-ErpFlow -Config $script:Cfg -Reset -Inputs @(
            '2',            # Ventas
            '1',            # Nuevo pedido
            'CLI001',       # Cliente
            'PROD-SIN-STOCK',
            '999999',       # Cantidad imposible
            'S'             # Confirmar
        )
        $out | Should -Match 'stock insuficiente|sin stock disponible'
        $out | Should -Not -Match 'Pedido registrado'
    }

    It 'avisa al vender a un cliente que supera su limite de credito' -Skip {
        # PLANTILLA.
        $out = Invoke-ErpFlow -Config $script:Cfg -Reset -Inputs @('2','1','CLI-MOROSO','PROD-100','1','S')
        $out | Should -Match 'limite de credito|saldo vencido'
    }
}
