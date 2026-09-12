<#
extract_word.ps1 - Extract text from .doc / .docx using the locally installed Word.

WHY: .doc (Word 97-2003, OLE) cannot be parsed by standard libraries, and
     hand-parsing word/document.xml destroys table structure. Word itself
     handles both correctly, at zero AI cost.

USAGE:
    pwsh -File extract_word.ps1 -In <input file> -Out <utf8 output>

NOTES:
  * Read-only: the source file is never modified.
  * Macros are force-disabled (AutomationSecurity=3).
  * Word writes ANSI/GB18030 text; we decode it correctly and re-save as UTF-8.
  * We never call Quit() - if Word was already running for the user, quitting
    would close their documents. We only kill Word processes WE started.
  * This script is intentionally ASCII-only: Windows PowerShell 5.1 reads
    .ps1 files as ANSI when there is no BOM, which corrupts non-ASCII source.
#>
param(
    [Parameter(Mandatory = $true)][string]$In,
    [Parameter(Mandatory = $true)][string]$Out
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$tmp  = Join-Path $env:TEMP ("kb_word_" + [guid]::NewGuid().ToString('N') + ".txt")

$before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)

$word = $null
$doc  = $null
$stats = @{ pages = 0; paras = 0; tables = 0; chars = 0 }
$err = ""

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    try { $word.AutomationSecurity = 3 } catch { }   # 3 = force-disable macros

    $doc = $word.Documents.Open($In, $false, $true)  # ConfirmConversions=false, ReadOnly=true
    $stats.pages  = [int]$doc.ComputeStatistics(2)   # 2 = wdStatisticPages
    $stats.paras  = [int]$doc.Paragraphs.Count
    $stats.tables = [int]$doc.Tables.Count
    $stats.chars  = [int]$doc.Characters.Count

    if (Test-Path $tmp) { Remove-Item $tmp -Force }
    $doc.SaveAs2($tmp, 7)                            # 7 = wdFormatEncodedText
    $doc.Close(0)                                    # 0 = wdDoNotSaveChanges
    $doc = $null
}
catch {
    $err = $_.Exception.Message
}
finally {
    if ($doc)  { try { $doc.Close(0) } catch { } }
    # Do NOT call $word.Quit(): it may be the user's own Word instance.
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
    Start-Sleep -Milliseconds 300
    # Kill only Word processes that we started
    Get-Process WINWORD -ErrorAction SilentlyContinue |
        Where-Object { $before -notcontains $_.Id } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

if ($err) { Write-Output "ERR $err"; exit 2 }
if (-not (Test-Path $tmp)) { Write-Output "ERR no temp output produced"; exit 3 }

# Word wrote GB18030 (Chinese ANSI). Decode properly, then save as UTF-8.
$gb    = [System.Text.Encoding]::GetEncoding(54936)   # 54936 = GB18030
$bytes = [System.IO.File]::ReadAllBytes($tmp)
$text  = $gb.GetString($bytes)
Remove-Item $tmp -Force -ErrorAction SilentlyContinue

$text = $text -replace "`r`n", "`n" -replace "`r", "`n"
[System.IO.File]::WriteAllText($Out, $text, $utf8)

Write-Output ("OK pages={0} paras={1} tables={2} wordchars={3} outchars={4}" -f `
    $stats.pages, $stats.paras, $stats.tables, $stats.chars, $text.Length)
