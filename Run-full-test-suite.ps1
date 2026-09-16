<#
.SYNOPSIS
    The conformance rig for Windows - run everything GitHub Actions cannot, into one log.

.DESCRIPTION
    A sibling of Run-full-test-suite.sh, NOT a fork of it: the layer ids (L1, L2, L2-RO, L3, L4,
    L5, L6) mean exactly what they mean there, and the spec is the same
    (docs/superpowers/specs/2026-09-05-conformance-rig.md).

    It exists because that script refuses to run here - it is zsh and the rig is specified as a
    Mac (spec S6). That was a defensible choice for the browser/editor layers, whose recipe is
    Command-key based. It is not defensible for layers 1-5, which have no Mac dependency at all,
    and the cost of the gap was measured on 2026-09-15: a first Windows run of this repository's
    suite found 33 failures and two real security defects, none of which CI could see.

    TWO DELIBERATE DIFFERENCES FROM THE SH RIG, both worth knowing:

    1. -Version defaults to `tree`, not to the published wheel. The sh rig tests PyPI because a
       packaging error is invisible to a source test, and that is right for a release check. This
       one is for a developer mid-change on the platform CI does not cover, where the question is
       "does my working tree work". `-Version latest` or `-Version 0.53.0` gets the other
       behaviour, installing into a throwaway venv - and then, per spec S3, pytest is given
       `-o pythonpath=` so the checkout cannot silently shadow the wheel under test.

    2. Nothing in a bare run can block. L6 (interactive OAuth) is excluded unless -Interactive is
       passed, because its read-only half needs a SECOND browser consent - read-only has had its
       own token cache since #185 - and with nobody watching it hangs on run_local_server. That
       was measured, at 400 seconds, before being killed.

    SKIPPED IS NOT PASSED. Every layer reports PASS, FAIL or SKIP-with-a-reason, and the summary
    counts them separately. A layer that could not run because a credential was absent must never
    read as one that ran.

.PARAMETER Version
    `tree` (default) tests this checkout. `latest` or an explicit version installs that release
    into a throwaway venv under -LogDir and tests it instead.

.PARAMETER Layers
    Comma-separated layer ids. Default: lint,types,docs,1,2,2ro,3,4,5
    Extra ids beyond the sh rig's, named rather than renumbered so nothing collides:
      lint  ruff     types  mypy     docs  check_doc_claims     index  gen_audit_index --check

.PARAMETER Interactive
    Add L6 (tests/oauth). Expect a browser. The read-only test is excluded even here unless
    -SecondConsent is also given, because it is the one that hangs.

.PARAMETER SecondConsent
    With -Interactive, also run the read-only OAuth test. Be at the keyboard.

.PARAMETER Offline
    Only layers needing no network and no Drive: lint, types, docs, 1, 3.

.PARAMETER Check
    Report prerequisites and credentials, run no layers.

.PARAMETER SelfTest
    Exercise the log redactor against known secrets and exit. The redactor is what makes this
    log safe to hand to somebody, so it is not left as a check that has never failed.

.PARAMETER LogDir
    Where the log and any throwaway venv go. Default ~\.csa_gw_rig - OUTSIDE the checkout, on
    purpose, so a run cannot pollute the tree it is testing.

.EXAMPLE
    .\Run-full-test-suite.ps1
    .\Run-full-test-suite.ps1 -Check
    .\Run-full-test-suite.ps1 -Offline
    .\Run-full-test-suite.ps1 -Interactive
    .\Run-full-test-suite.ps1 -Version latest -Layers 1,3
#>
[CmdletBinding()]
param(
    [string]   $Version = 'tree',
    [string]   $Layers,
    [switch]   $Interactive,
    [switch]   $SecondConsent,
    [switch]   $Offline,
    [switch]   $Check,
    [switch]   $SelfTest,
    [string]   $LogDir = (Join-Path $env:USERPROFILE '.csa_gw_rig')
)

$ErrorActionPreference = 'Stop'
$RepoDir = $PSScriptRoot
Set-Location $RepoDir

# --- layer selection --------------------------------------------------------------------------
$DefaultLayers = 'lint,types,docs,index,1,2,2ro,3,4,5'
$OfflineLayers = 'lint,types,docs,index,1,3'
if (-not $Layers) { $Layers = if ($Offline) { $OfflineLayers } else { $DefaultLayers } }
if ($Interactive -and $Layers -notmatch '(^|,)6(,|$)') { $Layers = "$Layers,6" }
$Wanted = $Layers.Split(',') | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }

# --- log --------------------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp   = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogDir "run-$Stamp.log"
New-Item -ItemType File -Path $LogFile | Out-Null

$Results  = [System.Collections.ArrayList]::new()
$Failed   = 0
$Skipped  = 0

# REDACTION. This log is written to be pasted into an issue or handed to a model, so it must not
# carry the things `_environment.py` refuses to report for the same reason. Home directory and
# username are rewritten on every line. Secrets are never echoed at all - no layer prints a token
# or a client secret, and `-Check` reports credentials by PRESENCE, never by content.
$HomeRe = [regex]::Escape($env:USERPROFILE)
$UserRe = [regex]::Escape($env:USERNAME)

# DRIVE FILE IDS ARE REDACTED, and this is the one that is easy to miss. `_environment.py` refuses
# to report them and says why: "a Drive file id is not a secret in the cryptographic sense and is
# very much a secret in the practical one: it is a working link to a document." L2, L4 and L5 all
# print ids, so without this the file you hand somebody contains working links into your Drive -
# which defeats the entire reason this log exists.
#
# Replaced by a short STABLE hash rather than a constant, so two mentions of the same file still
# read as the same file and a trace stays followable. Requires both a letter and a digit, so a
# run of dashes or a word is not mistaken for an id.
$IdRe = [regex]'(?<![A-Za-z0-9_-])(?=[A-Za-z0-9_-]*[0-9])(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{25,50}(?![A-Za-z0-9_-])'
$IdMap = @{}
function Get-IdAlias([string]$Id) {
    if (-not $IdMap.ContainsKey($Id)) {
        $md5   = [Security.Cryptography.MD5]::Create()
        $bytes = $md5.ComputeHash([Text.Encoding]::UTF8.GetBytes($Id))
        $IdMap[$Id] = '<file-' + (($bytes[0..2] | ForEach-Object { $_.ToString('x2') }) -join '') + '>'
    }
    return $IdMap[$Id]
}

function Protect-Line([string]$Line) {
    if ($null -eq $Line) { return '' }
    $out = $Line -replace $HomeRe, '~'
    $out = $out -replace $UserRe, '<user>'
    $out = $IdRe.Replace($out, { param($m) Get-IdAlias $m.Value })
    return $out
}

function Write-Log([string]$Text) { Add-Content -Path $LogFile -Value (Protect-Line $Text) -Encoding utf8 }
function Say([string]$Text, [string]$Colour = 'Gray') {
    Write-Host (Protect-Line $Text) -ForegroundColor $Colour
    Write-Log $Text
}
# ASCII ONLY, DELIBERATELY - and this file is the reason the rule is written down here.
# Windows PowerShell 5.1 reads a BOM-less script as ANSI (cp1252), so a box-drawing separator
# became mojibake and the file failed to PARSE - reported as "string is missing the terminator"
# 230 lines away from the actual character. pwsh 7 reads UTF-8 and was perfectly happy, so this
# is invisible on a modern shell. Saving with a BOM also fixes it and is what PowerShell's own
# docs suggest, but that is the byte that broke #449 at the other end of this same repository,
# and ASCII costs nothing.
function Section([string]$Title) {
    Say ''
    Say "--------- $Title" 'Cyan'
}

# --- interpreter ------------------------------------------------------------------------------
$TreeVenvPy = Join-Path $RepoDir '.venv\Scripts\python.exe'
$PyArgsExtra = @()          # `-o pythonpath=` only when a WHEEL is under test (spec S3)

function Resolve-Interpreter {
    if ($Version -eq 'tree') {
        if (-not (Test-Path $TreeVenvPy)) {
            Say "  ! no .venv in the checkout. Create one with:" 'Yellow'
            Say "      uv venv; uv pip install -e `".[dev,mcp]`"" 'Yellow'
            return $null
        }
        return $TreeVenvPy
    }
    # A release, in a throwaway venv OUTSIDE the checkout.
    $spec   = if ($Version -eq 'latest') { 'csa-google-workspace[mcp]' } else { "csa-google-workspace[mcp]==$Version" }
    $venv   = Join-Path $LogDir "venv-$Version"
    $venvPy = Join-Path $venv 'Scripts\python.exe'
    Say "  installing $spec into $venv ..."
    if (-not (Test-Path $venvPy)) {
        & python -m venv $venv 2>&1 | ForEach-Object { Write-Log $_ }
    }
    & $venvPy -m pip install --quiet --upgrade $spec 2>&1 | ForEach-Object { Write-Log $_ }
    if ($LASTEXITCODE -ne 0) { Say "  ! could not install $spec" 'Red'; return $null }
    # S3: without this, `pythonpath = ["src"]` in pyproject silently shadows the installed wheel,
    # so the run tests the checkout while REPORTING the release. The trap this rig was written for.
    $script:PyArgsExtra = @('-o', 'pythonpath=')
    return $venvPy
}

# --- layer runner -----------------------------------------------------------------------------
function Test-Wanted([string]$Id) { return $Wanted -contains $Id.ToLower() }

# `L` is the sh rig's prefix for its NUMBERED layers. The named ones here are additions, not
# renumberings, so they are not dressed up as layers they are not.
function Format-LayerId([string]$Id) { if ($Id -match '^\d') { "L$Id" } else { $Id } }

function Skip-Layer([string]$Id, [string]$Desc, [string]$Why) {
    Say ("  SKIP  {0,-6} {1}" -f (Format-LayerId $Id), $Desc) 'Yellow'
    Say "        reason: $Why" 'Yellow'
    [void]$Results.Add([pscustomobject]@{ Layer = (Format-LayerId $Id); Outcome = 'SKIP'; Detail = $Why })
    $script:Skipped++
}

function Invoke-Layer {
    param([string]$Id, [string]$Desc, [string[]]$Command)
    if (-not (Test-Wanted $Id)) { return }
    Section "$(Format-LayerId $Id) - $Desc"
    Write-Log "`$ $($Command -join ' ')"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & $Command[0] @($Command[1..($Command.Count - 1)]) 2>&1 | ForEach-Object { Write-Log ($_ | Out-String).TrimEnd() }
    $code = $LASTEXITCODE
    $sw.Stop()
    $took = '{0:n0}s' -f $sw.Elapsed.TotalSeconds
    if ($code -eq 0) {
        Say ("  PASS  {0,-6} {1} ({2})" -f (Format-LayerId $Id), $Desc, $took) 'Green'
        [void]$Results.Add([pscustomobject]@{ Layer = (Format-LayerId $Id); Outcome = 'PASS'; Detail = $took })
    } else {
        Say ("  FAIL  {0,-6} {1} (exit {2}, {3})" -f (Format-LayerId $Id), $Desc, $code, $took) 'Red'
        [void]$Results.Add([pscustomobject]@{ Layer = (Format-LayerId $Id); Outcome = 'FAIL'; Detail = "exit $code after $took" })
        $script:Failed++
    }
}

# --- prerequisites ----------------------------------------------------------------------------
Say "csa-google-workspace - conformance rig (Windows)" 'White'
Write-Host "log: $LogFile" -ForegroundColor White
Write-Log "log file: (this file)"
Say ''

Section 'Prerequisites'
$ConfigDir     = Join-Path $env:USERPROFILE '.csa_google_workspace'
$ClientSecrets = if ($env:CSA_GW_CLIENT_SECRETS) { $env:CSA_GW_CLIENT_SECRETS } else { Join-Path $ConfigDir 'client_secret.json' }
$TokenRw       = if ($env:CSA_GW_TOKEN) { $env:CSA_GW_TOKEN } else { Join-Path $ConfigDir 'token.json' }
$TokenRo       = [IO.Path]::ChangeExtension($TokenRw, $null) + 'readonly.json'
$TokenRo       = $TokenRw -replace '\.json$', '.readonly.json'

$HasSecrets = Test-Path $ClientSecrets
$HasRw      = Test-Path $TokenRw
$HasRo      = Test-Path $TokenRo

Say ("  client secrets : {0}" -f $(if ($HasSecrets) { 'present' } else { 'ABSENT' }))
Say ("  read-write token: {0}" -f $(if ($HasRw) { 'present' } else { 'ABSENT - run `login`' }))
Say ("  read-only token : {0}" -f $(if ($HasRo) { 'present' } else { 'absent - L2-RO will skip' }))
Say ("  layers requested: {0}" -f ($Wanted -join ','))
Say ("  version under test: {0}" -f $Version)

$Py = Resolve-Interpreter
if (-not $Py) { Say ''; Say "Stopped: no usable interpreter. See $LogFile" 'Red'; exit 2 }

# What is actually under test - recorded because `--version` alone cannot tell you whether an
# unreleased fix is present, which cost real confusion on 2026-09-15.
Section 'Version under test'
# A TEMP FILE, not `python -c`. Windows PowerShell 5.1 mangles quotes when passing a native
# argument, so any `-c` payload containing `"` arrives as a syntax error - while pwsh 7 passes it
# perfectly. Same 5.1-vs-7 divergence family as #449, and a file has no quoting to get wrong.
$probeFile = Join-Path $LogDir 'probe.py'
@'
import os, sys
import csa_google_workspace as pkg
from csa_google_workspace import auth
print("package version :", pkg.__version__)
print("package path    :", os.path.dirname(pkg.__file__))
print("python          :", sys.version.split()[0])
print("read_client_secrets present :", hasattr(auth, "read_client_secrets"))
print("file_is_owner_only present  :", hasattr(auth, "file_is_owner_only"))
'@ | Set-Content -Path $probeFile -Encoding ascii
& $Py $probeFile 2>&1 | ForEach-Object { Say ("  " + ($_ | Out-String).TrimEnd()) }
try {
    $sha = (& git rev-parse --short HEAD 2>$null)
    $dirty = (& git status --porcelain 2>$null)
    Say ("  git commit      : {0}{1}" -f $sha, $(if ($dirty) { ' (working tree DIRTY)' } else { '' }))
} catch { Say '  git commit      : unknown' }

if ($SelfTest) {
    # THE REDACTOR IS THE SECURITY-RELEVANT PART OF THIS SCRIPT, so it is not left untested.
    # It is what makes the log safe to paste into an issue, and a redactor nobody exercises is
    # the "check that has never failed is not yet a check" trap with a credential behind it.
    Section 'Self-test: redaction'
    $id1 = '16Yao8wL68IsPB3mFflFVg2ToAepR2w0S'
    $id2 = '1AbCdEfGhIjKlMnOpQrStUvWxYz012345'
    $cases = @(
        @{ In = "created $id1 in $id2"; MustNot = @($id1, $id2) }
        @{ In = "same file again $id1";  MustNot = @($id1) }
        @{ In = "path $env:USERPROFILE\GitHub and user $env:USERNAME"; MustNot = @($env:USERPROFILE, $env:USERNAME) }
    )
    $bad = 0
    foreach ($c in $cases) {
        $got = Protect-Line $c.In
        foreach ($secret in $c.MustNot) {
            if ($got -like "*$secret*") { Say "  LEAK: '$secret' survived -> $got" 'Red'; $bad++ }
        }
        Write-Log "  ok: $got"
    }
    # Stable aliasing: the same id must read the same way twice, or a trace is unfollowable.
    if ((Protect-Line $id1) -ne (Protect-Line $id1)) { Say '  UNSTABLE alias for one id' 'Red'; $bad++ }
    # And a run of dashes is not an id.
    if ((Protect-Line '--------------------------------') -match 'file-') { Say '  false positive on dashes' 'Red'; $bad++ }
    if ($bad -eq 0) { Say '  PASS  redaction: ids, home and username all removed; aliases stable' 'Green' }
    else            { Say "  FAIL  redaction: $bad problem(s)" 'Red' }
    Write-Host "log: $LogFile" -ForegroundColor White
    exit $(if ($bad) { 1 } else { 0 })
}

if ($Check) {
    Say ''
    Say "Prerequisites only (-Check). No layers ran." 'Yellow'
    Write-Host "log: $LogFile" -ForegroundColor White
    exit 0
}

# --- the layers -------------------------------------------------------------------------------
Invoke-Layer 'lint'  'ruff'                 @($Py, '-m', 'ruff', 'check', 'src', 'tests')
Invoke-Layer 'types' 'mypy'                 @($Py, '-m', 'mypy')
Invoke-Layer 'docs'  'doc claims'           @($Py, 'scripts/check_doc_claims.py')
Invoke-Layer 'index' 'audit index'          @($Py, 'scripts/gen_audit_index.py', '--check')

Invoke-Layer '1' 'offline unit suite' (@($Py, '-m', 'pytest', '-q') + $PyArgsExtra +
    @('tests/', '--ignore=tests/integration', '--ignore=tests/oauth'))

if (Test-Wanted '2') {
    if (-not $HasRw) { Skip-Layer '2' 'live integration suite' 'no read-write token; run `login`' }
    else {
        $env:CSA_GW_INTEGRATION = '1'; $env:CSA_GW_CLIENT_SECRETS = $ClientSecrets
        Invoke-Layer '2' 'live integration suite' (@($Py, '-m', 'pytest', '-q') + $PyArgsExtra + @('tests/integration/'))
        Remove-Item Env:CSA_GW_INTEGRATION -ErrorAction SilentlyContinue
    }
}

if (Test-Wanted '2ro') {
    if (-not $HasRo) {
        # A NEGATIVE layer: it proves Google itself refuses a write, which is categorically
        # stronger than our own guard refusing one. Skipping it is a real loss, so say so.
        Skip-Layer '2ro' 'read-only is refused BY GOOGLE' `
            'no read-only token. `$env:CSA_GW_READ_ONLY="1"` then `login` - it uses its own cache (#185)'
    } else {
        $env:CSA_GW_INTEGRATION = '1'; $env:CSA_GW_CLIENT_SECRETS = $ClientSecrets
        Invoke-Layer '2ro' 'read-only is refused BY GOOGLE' (@($Py, '-m', 'pytest', '-q') + $PyArgsExtra +
            @('tests/integration/test_read_only_is_enforced_by_google.py'))
        Remove-Item Env:CSA_GW_INTEGRATION -ErrorAction SilentlyContinue
    }
}

Invoke-Layer '3' 'MCP server smoke' @($Py, 'scripts/mcp_smoke.py')

if (Test-Wanted '4') {
    if (-not $HasRw) { Skip-Layer '4' 'zoo specimens still say what the repo claims' 'no read-write token' }
    else { Invoke-Layer '4' 'zoo specimens still say what the repo claims' @($Py, 'experiments/zoo/verify.py') }
}

if (Test-Wanted '5') {
    if (-not $HasRw) { Skip-Layer '5' 'demo --auto (guided end-to-end)' 'no read-write token' }
    else { Invoke-Layer '5' 'demo --auto (guided end-to-end)' @($Py, '-m', 'csa_google_workspace.mcp', 'demo', '--auto') }
}

if (Test-Wanted '6') {
    if (-not $HasSecrets) { Skip-Layer '6' 'interactive OAuth' 'no client secrets' }
    else {
        $env:CSA_GW_OAUTH = '1'; $env:CSA_GW_CLIENT_SECRETS = $ClientSecrets
        # -k "not read_only" unless -SecondConsent: read-only has its own token cache since #185,
        # so that test opens a SECOND browser consent and hangs when nobody is watching.
        $sel = if ($SecondConsent) { @() } else { @('-k', 'not read_only') }
        Invoke-Layer '6' 'interactive OAuth (browser)' (@($Py, '-m', 'pytest', '-q') + $PyArgsExtra + @('tests/oauth') + $sel)
        Remove-Item Env:CSA_GW_OAUTH -ErrorAction SilentlyContinue
    }
}

Remove-Item Env:CSA_GW_CLIENT_SECRETS -ErrorAction SilentlyContinue

# --- summary ----------------------------------------------------------------------------------
$Passed = ($Results | Where-Object Outcome -eq 'PASS').Count
$Verdict = if ($Failed -gt 0) { 'FAILED' } elseif ($Skipped -gt 0) { 'PASSED (with skips)' } else { 'PASSED' }

$summary = [System.Collections.ArrayList]::new()
[void]$summary.Add('=============================================================')
[void]$summary.Add(" csa-google-workspace conformance rig (Windows) - $Verdict")
[void]$summary.Add(" $(Get-Date -Format 'u')   version under test: $Version")
[void]$summary.Add(" passed $Passed   failed $Failed   skipped $Skipped")
[void]$summary.Add('-------------------------------------------------------------')
foreach ($r in $Results) { [void]$summary.Add((' {0,-8} {1,-5} {2}' -f $r.Layer, $r.Outcome, $r.Detail)) }
if ($Skipped -gt 0) {
    [void]$summary.Add('-------------------------------------------------------------')
    [void]$summary.Add(' SKIPPED IS NOT PASSED - a layer that could not run asserted nothing.')
}
[void]$summary.Add('=============================================================')
[void]$summary.Add('')

# Prepended, so whoever opens this file reads the verdict before the scrollback.
$body = Get-Content -Path $LogFile -Encoding utf8
Set-Content -Path $LogFile -Value ($summary + $body) -Encoding utf8

Write-Host ''
foreach ($line in $summary) { Write-Host (Protect-Line $line) -ForegroundColor $(if ($Failed) { 'Red' } else { 'Green' }) }
# The FULL path, unredacted, on the console only. The console is not what gets pasted into an
# issue - the log file is - and a redacted path is one you cannot hand to anybody.
Write-Host "log: $LogFile" -ForegroundColor White
Write-Host ''

exit $(if ($Failed -gt 0) { 1 } else { 0 })
