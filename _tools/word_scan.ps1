<#
word_scan.ps1 - Batch-read the first N chars of every .doc/.docx under a folder,
                using ONE Word instance, and emit one JSON object per file (JSONL).

USAGE:
    powershell -File word_scan.ps1 -Root <dir> -Out <jsonl> [-MaxChars 3000] [-Limit 0]

GOTCHAS SOLVED HERE (every one of these was hit for real on this machine):
  1. An INVISIBLE Word automation instance EXITS when its LAST document closes.
     After that, $word is a dead COM object and the next Open() fails with
     "You cannot call a method on a null-valued expression".
     Fix: keep the FIRST successfully opened document as an anchor and close it
     only at the very end. (Documents.Add() also hangs here - do not use it.)
  2. $doc.Range(0,$n) HANGS under PowerShell 5.1 + Word 2007 (ref parameters).
     Fix: use the plain property $doc.Content.Text and substring it.
  3. Quit() frequently fails with 0x800706BE. Never rely on it - kill only the
     Word processes WE started instead.

NOTES:
  * Read-only: source files are never modified. Macros force-disabled.
  * ASCII-only source on purpose (PS 5.1 reads .ps1 as ANSI when there is no BOM).
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
    Where-Object { $_.Extension -in '.doc', '.docx' -and $_.BaseName -notmatch '\(\d+\)$' })
if ($Limit -gt 0) { $files = @($files | Select-Object -First $Limit) }
Write-Output ("FILES " + $files.Count)

$before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$word = $null
$anchor = $null
$n = 0
$ok = 0
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    try { $word.AutomationSecurity = 3 } catch { }

    foreach ($f in $files) {
        $n++
        $rec = [ordered]@{ path = $f.FullName; size = $f.Length; pages = 0; ok = $false; text = ""; err = "" }
        $doc = $null
        try {
            $doc = $word.Documents.Open($f.FullName, $false, $true)
            try { $rec.pages = [int]$doc.ComputeStatistics(2) } catch { $rec.pages = 0 }
            $t = [string]$doc.Content.Text
            if ($t.Length -gt $MaxChars) { $t = $t.Substring(0, $MaxChars) }
            $rec.text = $t
            $rec.ok = $true
            $ok++
            if ($null -eq $anchor) { $anchor = $doc } else { $doc.Close(0) }
            $doc = $null
        }
        catch {
            $rec.err = "[$($_.Exception.GetType().Name)] $($_.Exception.Message)"
            if ($doc) { try { $doc.Close(0) } catch { } }
            $doc = $null
        }
        [System.IO.File]::AppendAllText($Out, (($rec | ConvertTo-Json -Compress) + "`n"), $utf8)
        if ($n % 25 -eq 0) { Write-Output ("PROGRESS " + $n + "/" + $files.Count + " ok=" + $ok) }
    }
}
catch {
    Write-Output ("FATAL " + $_.Exception.Message)
}
finally {
    if ($anchor) { try { $anchor.Close(0) } catch { } }
    if ($word) { try { $word.Quit() } catch { } }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
    Start-Sleep -Milliseconds 500
    Get-Process WINWORD -ErrorAction SilentlyContinue |
        Where-Object { $before -notcontains $_.Id } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}
Write-Output ("DONE total=" + $n + " ok=" + $ok)
