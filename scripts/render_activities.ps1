param(
  [string]$ActivitiesDir = (Join-Path $PSScriptRoot "..\docs\activities"),
  [string]$PlantUmlJar = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $ActivitiesDir)) {
  throw "Activities directory not found: $ActivitiesDir"
}

if (-not $PlantUmlJar) {
  $cacheDir = Join-Path $PSScriptRoot '.cache'
  if (-not (Test-Path $cacheDir)) {
    New-Item -ItemType Directory -Path $cacheDir | Out-Null
  }
  $PlantUmlJar = Join-Path $cacheDir 'plantuml.jar'
}

if (-not (Test-Path $PlantUmlJar)) {
  $url = 'https://github.com/plantuml/plantuml/releases/latest/download/plantuml.jar'
  Invoke-WebRequest -Uri $url -OutFile $PlantUmlJar
}

if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
  throw 'Java not found on PATH. Install Java 17+ or add java to PATH.'
}

Get-ChildItem -Path $ActivitiesDir -Recurse -Include *.png,*.svg | Remove-Item -Force -ErrorAction SilentlyContinue

$pumlFiles = Get-ChildItem -Path $ActivitiesDir -Filter *.puml
if (-not $pumlFiles) {
  throw "No .puml files found in $ActivitiesDir"
}

foreach ($file in $pumlFiles) {
  & java -jar $PlantUmlJar -charset UTF-8 -tpng $file.FullName
}

Add-Type -AssemblyName System.Drawing
Get-ChildItem -Path $ActivitiesDir -Filter *.png | ForEach-Object {
  $path = $_.FullName
  $tmp = "$path.tmp.png"
  $orig = [System.Drawing.Bitmap]::FromFile($path)
  $bmp = New-Object System.Drawing.Bitmap(
    $orig.Width,
    $orig.Height,
    [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
  )
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.DrawImage($orig, 0, 0, $orig.Width, $orig.Height)
  $blackThreshold = 40
  $width = $bmp.Width
  $height = $bmp.Height
  $lineCols = New-Object 'System.Collections.Generic.HashSet[int]'
  $minLineCount = [int]($height * 0.9)
  for ($x = 0; $x -lt $width; $x++) {
    $count = 0
    for ($y = 0; $y -lt $height; $y++) {
      $c = $bmp.GetPixel($x, $y)
      if ($c.R -lt $blackThreshold -and $c.G -lt $blackThreshold -and $c.B -lt $blackThreshold) {
        $count++
      }
    }
    if ($count -ge $minLineCount) {
      $lineCols.Add($x) | Out-Null
    }
  }
  $rowHasContent = New-Object bool[] $height
  for ($y = 0; $y -lt $height; $y++) {
    $hasContent = $false
    for ($x = 1; $x -lt ($width - 1); $x++) {
      if ($lineCols.Contains($x)) {
        continue
      }
      $c = $bmp.GetPixel($x, $y)
      if ($c.R -lt $blackThreshold -and $c.G -lt $blackThreshold -and $c.B -lt $blackThreshold) {
        $hasContent = $true
        break
      }
    }
    $rowHasContent[$y] = $hasContent
  }
  $maxHeaderScan = [Math]::Min([int]($height * 0.5), 220)
  $firstContent = -1
  for ($y = 1; $y -lt $maxHeaderScan; $y++) {
    if ($rowHasContent[$y]) {
      $firstContent = $y
      break
    }
  }
  $titleBottom = -1
  $firstBody = -1
  if ($firstContent -ge 0) {
    $lastContent = $firstContent
    $gapCount = 0
    for ($y = $firstContent + 1; $y -lt $maxHeaderScan; $y++) {
      if ($rowHasContent[$y]) {
        $lastContent = $y
        $gapCount = 0
      } else {
        $gapCount++
        if ($gapCount -ge 3) {
          $titleBottom = $lastContent
          break
        }
      }
    }
    if ($titleBottom -ge 0) {
      for ($y = $titleBottom + 1; $y -lt ($height - 1); $y++) {
        if ($rowHasContent[$y]) {
          $firstBody = $y
          break
        }
      }
    }
  }
  $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::Black, 1)
  if ($titleBottom -ge 0 -and $firstBody -gt $titleBottom) {
    $yLine = $titleBottom + 2
    if ($yLine -ge $firstBody) {
      $yLine = $firstBody - 2
    }
    if ($yLine -gt 0 -and $yLine -lt ($height - 1)) {
      $g.DrawLine($pen, 0, $yLine, $width - 1, $yLine)
    }
  }
  $g.DrawRectangle($pen, 0, 0, $bmp.Width - 1, $bmp.Height - 1)
  $g.Dispose()
  $orig.Dispose()
  $bmp.Save($tmp, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  Move-Item -Force $tmp $path
}

Write-Host "Rendered $($pumlFiles.Count) diagrams to PNG with borders in $ActivitiesDir"
