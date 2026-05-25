[CmdletBinding()]
param(
    [string]$SourceDir = 'F:\yangzhou_edf',
    [string]$RepeatDir = 'F:\yangzhou_edf_repeat',
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-IndexedEdfInfo {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo]$File
    )

    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($File.Name)
    $pattern = '^(?<Person>.+?)\s*_\._\s*(?:\((?<Index>\d+)\)|\uFF08(?<IndexCn>\d+)\uFF09)$'

    if ($baseName -notmatch $pattern) {
        return $null
    }

    $indexText = if ($matches.Index) { $matches.Index } else { $matches.IndexCn }

    return [PSCustomObject]@{
        FullName = $File.FullName
        Name     = $File.Name
        Person   = $matches.Person.Trim()
        Index    = [int]$indexText
        Length   = [int64]$File.Length
    }
}

function Get-UniqueDestinationPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Directory,

        [Parameter(Mandatory = $true)]
        [string]$FileName
    )

    $targetPath = Join-Path -Path $Directory -ChildPath $FileName
    if (-not (Test-Path -LiteralPath $targetPath)) {
        return $targetPath
    }

    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($FileName)
    $extension = [System.IO.Path]::GetExtension($FileName)
    $counter = 1

    do {
        $candidate = Join-Path -Path $Directory -ChildPath ("{0}__dup_move_{1}{2}" -f $baseName, $counter, $extension)
        $counter++
    } while (Test-Path -LiteralPath $candidate)

    return $candidate
}

if (-not (Test-Path -LiteralPath $SourceDir)) {
    throw "Source directory not found: $SourceDir"
}

$resolvedSource = (Resolve-Path -LiteralPath $SourceDir).Path
$resolvedRepeat = $RepeatDir

if (Test-Path -LiteralPath $RepeatDir) {
    $resolvedRepeat = (Resolve-Path -LiteralPath $RepeatDir).Path
}

if ($resolvedSource -eq $resolvedRepeat) {
    throw 'SourceDir and RepeatDir cannot be the same directory.'
}

$allEdfFiles = @(
    Get-ChildItem -LiteralPath $SourceDir |
        Where-Object {
            -not $_.PSIsContainer -and
            [string]::Equals($_.Extension, '.edf', [System.StringComparison]::OrdinalIgnoreCase)
        }
)

$parsedFiles = @(
    foreach ($file in $allEdfFiles) {
        $info = Get-IndexedEdfInfo -File $file
        if ($null -ne $info) {
            $info
        }
    }
)

$moveList = New-Object System.Collections.Generic.List[object]

foreach ($personGroup in ($parsedFiles | Group-Object -Property Person)) {
    foreach ($sizeGroup in ($personGroup.Group | Group-Object -Property Length)) {
        $ordered = @(
            $sizeGroup.Group |
                Sort-Object -Property @{ Expression = 'Index'; Ascending = $true }, @{ Expression = 'Name'; Ascending = $true }
        )

        if ($ordered.Count -le 1) {
            continue
        }

        $keeper = $ordered[0]

        for ($i = 1; $i -lt $ordered.Count; $i++) {
            $duplicate = $ordered[$i]
            $moveList.Add([PSCustomObject]@{
                Person     = $duplicate.Person
                Length     = $duplicate.Length
                KeepName   = $keeper.Name
                KeepIndex  = $keeper.Index
                MoveName   = $duplicate.Name
                MoveIndex  = $duplicate.Index
                SourcePath = $duplicate.FullName
            }) | Out-Null
        }
    }
}

$sortedMoves = @(
    $moveList |
        Sort-Object -Property @{ Expression = 'Person'; Ascending = $true }, @{ Expression = 'Length'; Ascending = $true }, @{ Expression = 'MoveIndex'; Ascending = $true }, @{ Expression = 'MoveName'; Ascending = $true }
)

$skippedCount = $allEdfFiles.Count - $parsedFiles.Count

Write-Host ("SourceDir: {0}" -f $SourceDir)
Write-Host ("RepeatDir: {0}" -f $RepeatDir)
Write-Host ("EDF files scanned: {0}" -f $allEdfFiles.Count)
Write-Host ("Matched *_._(n) pattern: {0}" -f $parsedFiles.Count)
Write-Host ("Skipped (name not matched): {0}" -f $skippedCount)
Write-Host ("Duplicate files to move: {0}" -f $sortedMoves.Count)

if ($sortedMoves.Count -eq 0) {
    Write-Host 'No duplicates matched the current rules.'
    return
}

$sortedMoves |
    Select-Object Person, Length, KeepName, MoveName |
    Format-Table -AutoSize

if (-not $Apply) {
    Write-Host ''
    Write-Host 'Preview only. No files were moved.'
    Write-Host "Run again with -Apply to move duplicates into the repeat folder."
    return
}

if (-not (Test-Path -LiteralPath $RepeatDir)) {
    New-Item -ItemType Directory -Path $RepeatDir | Out-Null
}

$movedCount = 0

foreach ($item in $sortedMoves) {
    $destinationPath = Get-UniqueDestinationPath -Directory $RepeatDir -FileName $item.MoveName
    Move-Item -LiteralPath $item.SourcePath -Destination $destinationPath
    $movedCount++
    Write-Host ("Moved: {0} -> {1}" -f $item.MoveName, $destinationPath)
}

Write-Host ''
Write-Host ("Done. Moved {0} duplicate file(s) to {1}" -f $movedCount, $RepeatDir)
