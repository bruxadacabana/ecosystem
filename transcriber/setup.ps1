# setup.ps1 - Instalacao automatica de dependencias portateis

param(
    [string]$BaseDir = $PSScriptRoot
)

$PortableDir = Join-Path $BaseDir "_portable"
$PythonDir   = Join-Path $PortableDir "python"
$FfmpegDir   = Join-Path $PortableDir "ffmpeg"
$PythonExe   = Join-Path $PythonDir   "python.exe"
$FfmpegExe   = Join-Path $FfmpegDir   "ffmpeg.exe"
$TempDir     = Join-Path $PortableDir "tmp"
$DoneFlag    = Join-Path $PortableDir ".setup_done"
$LogFile     = Join-Path $BaseDir "setup_log.txt"

function Write-Log {
    param([string]$Msg)
    $ts = (Get-Date).ToString("HH:mm:ss")
    "$ts  $Msg" | Add-Content $LogFile -Encoding UTF8
    Write-Host "$ts  $Msg"
}

if (Test-Path $LogFile) { Remove-Item $LogFile -Force }
Write-Log "=== INICIO DO SETUP ==="
Write-Log "BaseDir: $BaseDir"
Write-Log "PowerShell: $($PSVersionTable.PSVersion)"
Write-Log "OS: $([System.Environment]::OSVersion.VersionString)"

try {
    Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase
    Write-Log "WPF carregado OK"
} catch {
    Write-Log "AVISO: WPF nao disponivel: $_"
}

[xml]$xaml = @'
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    Title="Video Transcriber - Configuracao inicial"
    Width="540" Height="230"
    WindowStartupLocation="CenterScreen"
    ResizeMode="NoResize"
    Background="#1e1e2e">
  <Grid Margin="28">
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="16"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>
    <TextBlock Grid.Row="0"
               Text="Video Transcriber - Configuracao inicial"
               FontSize="15" FontWeight="Bold"
               Foreground="#cdd6f4" FontFamily="Segoe UI" Margin="0,0,0,8"/>
    <TextBlock Grid.Row="1" Name="StatusText" Text="Iniciando..."
               FontSize="10" Foreground="#a6adc8" FontFamily="Segoe UI"
               TextWrapping="Wrap" Margin="0,0,0,10"/>
    <ProgressBar Grid.Row="2" Name="ProgressBar"
                 Height="14" IsIndeterminate="True"
                 Background="#2a2a3e" Foreground="#5865F2" BorderThickness="0"/>
    <TextBlock Grid.Row="3" Margin="0,10,0,0"
               Text="Isso so acontece uma vez. Pode demorar alguns minutos."
               FontSize="9" Foreground="#6c7086" FontFamily="Segoe UI"
               TextWrapping="Wrap"/>
  </Grid>
</Window>
'@

$window   = $null
$statusTb = $null
$progress = $null

try {
    $reader   = New-Object System.Xml.XmlNodeReader $xaml
    $window   = [Windows.Markup.XamlReader]::Load($reader)
    $statusTb = $window.FindName("StatusText")
    $progress = $window.FindName("ProgressBar")
    $window.Show()
    Write-Log "Janela WPF aberta OK"
} catch {
    Write-Log "AVISO: Nao foi possivel abrir janela WPF: $_"
}

function Set-Status {
    param([string]$Msg, [switch]$Done)
    Write-Log $Msg
    if ($window) {
        $script:_msg  = $Msg
        $script:_done = $Done.IsPresent
        try {
            $window.Dispatcher.Invoke([action]{
                $statusTb.Text = $script:_msg
                if ($script:_done) {
                    $progress.IsIndeterminate = $false
                    $progress.Value = 100
                }
            })
        } catch { }
    }
}

function Close-Ui {
    if ($window) {
        try { $window.Dispatcher.Invoke([action]{ $window.Close() }) } catch { }
    }
}

function Exit-WithError {
    param([string]$Msg)
    Write-Log "ERRO FATAL: $Msg"
    Write-Log "=== LOG SALVO EM: $LogFile ==="
    if ($window) {
        $script:_errmsg = $Msg
        try {
            $window.Dispatcher.Invoke([action]{
                $statusTb.Text       = "ERRO: $script:_errmsg"
                $statusTb.Foreground = "#f38ba8"
                $progress.IsIndeterminate = $false
                $progress.Value      = 0
            })
        } catch { }
        Start-Sleep 4
        Close-Ui
    }
    exit 1
}

function Get-File {
    param([string]$Url, [string]$Dest, [string]$Label)
    Set-Status "Baixando $Label..."
    Write-Log "  URL: $Url"
    try {
        $wc = New-Object System.Net.WebClient
        $wc.Headers.Add("User-Agent", "Mozilla/5.0")
        $wc.DownloadFile($Url, $Dest)
        if (Test-Path $Dest) {
            $sz = (Get-Item $Dest).Length
            Write-Log "  Baixado: $sz bytes"
            if ($sz -lt 1000) {
                throw "Arquivo muito pequeno ($sz bytes) - possivel erro de rede."
            }
        } else {
            throw "Arquivo nao foi criado em disco."
        }
    } catch {
        Exit-WithError "Falha ao baixar ${Label}: $_"
    }
}

Write-Log "Criando diretorios..."
New-Item -ItemType Directory -Force -Path $PythonDir, $FfmpegDir, $TempDir | Out-Null

# ============================================================
# 1. Python completo (instalador silencioso na pasta _portable)
#    O Python embarcado NAO inclui tkinter - precisamos do instalador completo
# ============================================================
Write-Log "--- Python ---"
Write-Log "python.exe existe: $(Test-Path $PythonExe)"

if (-not (Test-Path $PythonExe)) {
    $pyInstaller = Join-Path $TempDir "python-installer.exe"
    Get-File "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" `
             $pyInstaller "Python 3.11 completo"

    Set-Status "Instalando Python (pode demorar 1-2 min)..."
    Write-Log "  Executando instalador silencioso em: $PythonDir"

    # Flags do instalador oficial do Python:
    # /quiet         = sem janelas
    # TargetDir      = pasta de destino
    # InstallAllUsers=0  = sem admin
    # Include_tcltk=1    = inclui tkinter
    # Include_pip=1      = inclui pip
    # Include_launcher=0 = sem launcher global
    # PrependPath=0      = nao mexe no PATH do sistema
    $args = @(
        "/quiet",
        "TargetDir=$PythonDir",
        "InstallAllUsers=0",
        "Include_tcltk=1",
        "Include_pip=1",
        "Include_launcher=0",
        "PrependPath=0",
        "Shortcuts=0",
        "AssociateFiles=0"
    )
    $proc = Start-Process -FilePath $pyInstaller -ArgumentList $args -Wait -PassThru
    Write-Log "  Instalador retornou: $($proc.ExitCode)"

    if (-not (Test-Path $PythonExe)) {
        Exit-WithError "Python nao foi instalado. Codigo: $($proc.ExitCode)"
    }

    # Verifica tkinter
    $tkTest = & $PythonExe -c "import tkinter; print('tkinter OK')" 2>&1
    Write-Log "  Teste tkinter: $tkTest"
    if ($LASTEXITCODE -ne 0) {
        Exit-WithError "tkinter nao disponivel apos instalacao."
    }
}

# pip ja vem no instalador completo
$pip = Join-Path $PythonDir "Scripts\pip.exe"
if (-not (Test-Path $pip)) {
    Exit-WithError "pip nao encontrado em: $pip"
}
Write-Log "  pip OK: $pip"

# ============================================================
# 2. FFmpeg
# ============================================================
Write-Log "--- FFmpeg ---"
Write-Log "ffmpeg.exe existe: $(Test-Path $FfmpegExe)"

if (-not (Test-Path $FfmpegExe)) {
    $ffUrl = "https://github.com/GyanD/codexffmpeg/releases/download/7.1/ffmpeg-7.1-essentials_build.zip"
    $ffZip = Join-Path $TempDir "ffmpeg.zip"
    Get-File $ffUrl $ffZip "FFmpeg"

    Set-Status "Extraindo FFmpeg..."
    $ffRaw = Join-Path $TempDir "ffmpeg_raw"
    Expand-Archive -Path $ffZip -DestinationPath $ffRaw -Force

    $found = Get-ChildItem $ffRaw -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
    if (-not $found) {
        Exit-WithError "ffmpeg.exe nao encontrado no ZIP baixado."
    }
    Get-ChildItem $found.DirectoryName -Filter "*.exe" |
        Copy-Item -Destination $FfmpegDir -Force
    Write-Log "  FFmpeg copiado de: $($found.DirectoryName)"
}

# ============================================================
# 3. Pacotes Python
# ============================================================
Write-Log "--- Pacotes Python ---"

function Invoke-Pip {
    param([string[]]$PipArgs)
    Write-Log "  pip $($PipArgs -join ' ')"
    $out = & $pip @PipArgs 2>&1
    $ec  = $LASTEXITCODE
    Write-Log "  exit: $ec"
    if ($out) { Write-Log "  output: $($out | Select-Object -Last 3 | Out-String)" }
    return $ec
}

Set-Status "Instalando yt-dlp..."
$ec = Invoke-Pip @("install", "--quiet", "--no-warn-script-location", "yt-dlp")
if ($ec -ne 0) { Exit-WithError "Falha ao instalar yt-dlp (codigo $ec)" }

Set-Status "Instalando openai-whisper e torch (download grande, aguarde)..."
$ec = Invoke-Pip @("install", "--quiet", "--no-warn-script-location", "openai-whisper")
if ($ec -ne 0) { Exit-WithError "Falha ao instalar openai-whisper (codigo $ec)" }

# ============================================================
# 4. Finalizar
# ============================================================
Set-Status "Limpando temporarios..."
Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue

"ok" | Set-Content $DoneFlag -Encoding ASCII
Write-Log "=== SETUP CONCLUIDO COM SUCESSO ==="
Set-Status "Tudo pronto! Abrindo o programa..." -Done
Start-Sleep 1
Close-Ui
