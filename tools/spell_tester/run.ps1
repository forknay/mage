# run.ps1 -- builds the tester if needed, then opens it.
#
# The executable serves the drawing page at http://127.0.0.1:8770/ and opens a
# browser at it. Leave this window open while testing: the engine lives in it,
# and every recognition it makes is logged here as well as shown on the page.
# Ctrl+C stops it.

param(
	# Rebuild even when the executable is newer than every source.
	[switch]$Force,
	# Do not open a browser -- useful when one is already pointed at the page.
	[switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $here "build.ps1") -Force:$Force
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$exeArgs = @()
if ($NoBrowser) { $exeArgs += "--no-browser" }
& (Join-Path $here "spell_tester.exe") @exeArgs
