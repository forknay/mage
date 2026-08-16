# build.ps1 -- compiles the standalone spell tester.
#
# Builds main.cpp together with the engine sources from the Godot project, so
# the tester is the same recognizer the game runs, not a copy of it. The shim/
# directory goes first on the include path to satisfy the sources' <JenovaSDK.h>
# include outside Godot.
#
# Uses g++ if it is on PATH, otherwise the MSVC that Jenova already relies on.
# Run .\run.ps1 instead if you just want to draw.

param(
	# Rebuild even when the executable is newer than every source.
	[switch]$Force
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$project = Resolve-Path (Join-Path $here "..\..\mage-godot")
$engine = Join-Path $project "scripts\spell_engine"
$exe = Join-Path $here "spell_tester.exe"

$sources = @(
	(Join-Path $here "main.cpp"),
	(Join-Path $engine "gesture_types.cpp"),
	(Join-Path $engine "merge_intersecting_strokes.cpp"),
	(Join-Path $engine "recognizer.cpp"),
	(Join-Path $engine "spell_engine.cpp"),
	(Join-Path $engine "spell_matcher.cpp")
)

foreach ($source in $sources) {
	if (-not (Test-Path $source)) { throw "missing source: $source" }
}

if (-not $Force -and (Test-Path $exe)) {
	$built = (Get-Item $exe).LastWriteTimeUtc
	$newest = ($sources | ForEach-Object { (Get-Item $_).LastWriteTimeUtc } | Measure-Object -Maximum).Maximum
	if ($built -gt $newest) {
		Write-Host "spell_tester.exe is up to date (build.ps1 -Force to rebuild anyway)"
		exit 0
	}
}

# shim first: <JenovaSDK.h> must resolve to ours, not to Jenova's real one.
$includes = @((Join-Path $here "shim"), $project)

$gpp = Get-Command g++ -ErrorAction SilentlyContinue
if ($gpp) {
	Write-Host "building with $($gpp.Source)"
	$gppArgs = @("-std=c++20", "-O2", "-o", $exe)
	foreach ($include in $includes) { $gppArgs += "-I$include" }
	$gppArgs += $sources
	$gppArgs += @("-lws2_32", "-lshell32")
	& $gpp.Source @gppArgs
	if ($LASTEXITCODE -ne 0) { throw "g++ failed with exit code $LASTEXITCODE" }
	Write-Host "built $exe"
	exit 0
}

# MSVC fallback: the same compiler bridge Jenova builds the game's C++ with.
$cl = Join-Path $project "Jenova\Packages\JenovaMSVCCompiler-Universal\Bin\cl.exe"
if (-not (Test-Path $cl)) {
	$cl = (Get-Command cl.exe -ErrorAction SilentlyContinue).Source
}
if (-not $cl) {
	throw "no compiler found -- install g++ (scoop install gcc) or Visual Studio's C++ tools"
}

Write-Host "building with $cl"
$objDir = Join-Path $here "obj"
New-Item -ItemType Directory -Force $objDir | Out-Null
$clArgs = @("/nologo", "/std:c++20", "/EHsc", "/O2", "/MD")
foreach ($include in $includes) { $clArgs += "/I$include" }
$clArgs += $sources
$clArgs += @("/Fo:$objDir\", "/Fe:$exe", "/link", "ws2_32.lib", "shell32.lib")
& $cl @clArgs
if ($LASTEXITCODE -ne 0) { throw "cl.exe failed with exit code $LASTEXITCODE" }
Write-Host "built $exe"
