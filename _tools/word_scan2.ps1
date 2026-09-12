<#
word_scan2.ps1 - Batch scan .doc/.docx by running extract_word.ps1 ONCE PER FILE
                 (one fresh PowerShell + Word process per document).

WHY NOT ONE LONG-LIVED WORD INSTANCE:
  On this machine (Office 2007 / Word 12.0 + PowerShell 5.1) a single invisible
  automation instance is unstable:
    * it exits when its last document closes -> dead COM object for the next file
    * keeping an anchor document open, or calling Documents.Add(), HANGS
  A fresh process per file was verified repeatedly to work, so we trade speed
  for reliability. ~5-8s per document, which is fine for a background run.

USAGE:
    powershell -File word_scan2.ps1 -Root <dir> -Out <jsonl> [-MaxChars 3000] [-Limit 0]

Read-only: source files are never modified.
ASCII-only source on purpose (PS 5.1 reads .ps1 as ANSI when there is no BOM).
#>
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$MaxChars = 3000,
    [int]$Limit = 0
)

$ErrorActionPreference = 'Continue'
$utf8 = New-Object System.Text.UTF8Encoding($false)
if (Test-Path $Out) { Remove-Item $Out -Force }

$files = @(Get-ChildItem -LiteralPath $Root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in '.doc', '.docx' -and $_.BaseName -notmatch '\(\d+\)$' } |
    Sort-Object FullName)
if ($Limit -gt 0) { $files = @($files | Select-Object -First $Limit) }
Write-Output ("FILES " + $files.Count)

$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $PSCommandPath }
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Definition }
$helper = Join-Path $here 'extract_word.ps1'
Write-Output ("HELPER [" + $helper + "] exists=" + (Test-Path $helper))
if (-not (Test-Path $helper)) { Write-Output "FATAL helper not found"; exit 4 }
$tmp = Join-Path $env:TEMP ("kb_one_" + [guid]::NewGuid().ToString('N') + ".txt")
$n = 0
$ok = 0
foreach ($f in $files) {
    $n++
    if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
    $r = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $helper -In $f.FullName -Out $tmp 2>&1
    $info = (($r | Out-String) -replace '[\r\n]+', ' ').Trim()

    $txt = ""
    $good = $false
    if (Test-Path $tmp) {
        try {
            $txt = [System.IO.File]::ReadAllText($tmp, [System.Text.Encoding]::UTF8)
            $good = $true
            $ok++
        }
        catch { $info = $info + " | read-back failed" }
    }
    if ($txt.Length -gt $MaxChars) { $txt = $txt.Substring(0, $MaxChars) }

    $pg = 0
    if ($info -match 'pages=(\d+)') { $pg = [int]$Matches[1] }

    $rec = [ordered]@{ path = $f.FullName; size = $f.Length; pages = $pg; ok = $good; text = $txt; err = $(if ($good) { "" } else { $info }) }
    [System.IO.File]::AppendAllText($Out, (($rec | ConvertTo-Json -Compress) + "`n"), $utf8)
    if ($n % 10 -eq 0) { Write-Output ("PROGRESS " + $n + "/" + $files.Count + " ok=" + $ok) }
}
Remove-Item $tmp -Force -ErrorAction SilentlyContinue
Write-Output ("DONE total=" + $n + " ok=" + $ok)
