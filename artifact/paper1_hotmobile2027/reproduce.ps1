param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$CandidateRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "paper1-hotmobile-replay-" + [guid]::NewGuid().ToString("N")
)
$PreviousNoBytecode = $env:PYTHONDONTWRITEBYTECODE

function Assert-ByteIdentical {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Frozen
    )

    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
        throw "Generated candidate is missing: $Candidate"
    }
    $CandidateHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Candidate).Hash
    $FrozenHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Frozen).Hash
    if ($CandidateHash -ne $FrozenHash) {
        throw "Generated candidate differs from frozen output: $Frozen"
    }
}

New-Item -ItemType Directory -Path $CandidateRoot | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"

Push-Location $RepoRoot
try {
    # Copy the exact allowlisted release into temporary space, then run the
    # committed reducer there. The accepted release remains read-only even
    # though the reducer's normal entry point writes its three outputs.
    $ReleaseFiles = Get-Content -LiteralPath (Join-Path $RepoRoot "FILES.txt")
    foreach ($Relative in $ReleaseFiles) {
        $Candidate = Join-Path $CandidateRoot $Relative
        $Parent = Split-Path -Parent $Candidate
        if (-not (Test-Path -LiteralPath $Parent)) {
            New-Item -ItemType Directory -Path $Parent -Force | Out-Null
        }
        Copy-Item -LiteralPath (Join-Path $RepoRoot $Relative) -Destination $Candidate
    }

    Push-Location $CandidateRoot
    try {
        & $Python -m src.report.paper1_hotmobile2027_workshop `
            --config "configs/paper1_hotmobile2027_replay.yaml" `
            --overwrite
        if ($LASTEXITCODE -ne 0) { throw "Paper 1 report generation failed." }
        & $Python -B -m src.report.paper1_corrected_runtime_v1 --output corrected-candidate.tex
        if ($LASTEXITCODE -ne 0) { throw "Corrected primary table generation failed." }
    } finally {
        Pop-Location
    }

    $Generated = @(
        "results/tables/paper1_hotmobile2027_workshop.json",
        "results/tables/paper1_hotmobile2027_workshop.md",
        "docs/paper/generated/paper1_hotmobile2027.tex"
    )
    foreach ($Relative in $Generated) {
        Assert-ByteIdentical `
            -Candidate (Join-Path $CandidateRoot $Relative) `
            -Frozen (Join-Path $RepoRoot $Relative)
    }
    Write-Host "PAPER1_HOTMOBILE_GENERATED_OUTPUTS_PASS files=$($Generated.Count)"
    Assert-ByteIdentical -Candidate (Join-Path $CandidateRoot "corrected-candidate.tex") `
        -Frozen (Join-Path $RepoRoot "docs/paper/generated/paper1_corrected_runtime_v1.tex")

    & $Python -m pytest `
        tests/test_paper1_hotmobile2027_report.py `
        tests/test_paper1_hotmobile2027_workshop.py `
        tests/test_paper1_hotmobile2027_artifact.py `
        tests/test_paper1_composition_artifact.py `
        tests/test_paper1_prompt_artifact.py `
        tests/test_paper1_corrected_artifact.py `
        tests/test_paper1_three_resolution_artifact.py `
        tests/test_paper1_release_inventory.py `
        --basetemp (Join-Path $CandidateRoot "pytest") `
        -p no:cacheprovider `
        -q
    if ($LASTEXITCODE -ne 0) { throw "Paper 1 focused tests failed." }

    & $Python "artifact/paper1_hotmobile2027/verify_hashes.py" `
        --manifest "artifact/paper1_hotmobile2027/expected_outputs.json"
    if ($LASTEXITCODE -ne 0) { throw "Paper 1 claims hash verification failed." }

    & $Python -B "artifact/paper1_hotmobile2027/verify_composition_audits.py"
    if ($LASTEXITCODE -ne 0) { throw "Composition successor evidence verification failed." }

    & $Python -B "artifact/paper1_hotmobile2027/verify_prompt_selection.py"
    if ($LASTEXITCODE -ne 0) { throw "Prompt-selection evidence verification failed." }
    & $Python -B "artifact/paper1_hotmobile2027/verify_corrected_runtime.py"
    if ($LASTEXITCODE -ne 0) { throw "Corrected-system capture verification failed." }

    & $Python -B "artifact/paper1_hotmobile2027/verify_180p_runtime.py"
    if ($LASTEXITCODE -ne 0) { throw "180p capture replay failed." }

    & $Python "artifact/paper1_hotmobile2027/verify_rk3566_summary.py"
    if ($LASTEXITCODE -ne 0) { throw "RK3566 compact evidence verification failed." }

    & $Python "artifact/paper1_hotmobile2027/verify_release.py"
    if ($LASTEXITCODE -ne 0) { throw "Paper 1 release hygiene verification failed." }
} finally {
    Pop-Location
    if ($null -eq $PreviousNoBytecode) {
        Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONDONTWRITEBYTECODE = $PreviousNoBytecode
    }
    if (Test-Path -LiteralPath $CandidateRoot) {
        $ResolvedCandidate = (Resolve-Path -LiteralPath $CandidateRoot).Path
        $ResolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        $Leaf = [System.IO.Path]::GetFileName($ResolvedCandidate)
        if (
            -not $ResolvedCandidate.StartsWith(
                $ResolvedTemp,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -or -not $Leaf.StartsWith("paper1-hotmobile-replay-")
        ) {
            throw "Refusing to remove unsafe temporary path: $ResolvedCandidate"
        }
        Remove-Item -LiteralPath $ResolvedCandidate -Recurse -Force
    }
}

Write-Host "PAPER1_HOTMOBILE_REPRODUCTION_PASS"
