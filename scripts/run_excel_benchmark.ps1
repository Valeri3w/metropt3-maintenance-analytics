param(
    [string]$OutputDirectory = (
        Join-Path $PSScriptRoot "..\artifacts\business_comparison"
    )
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

$workbookPath = Join-Path $outputRoot "manual_week_20200601.xlsx"
$jsonPath = Join-Path $outputRoot "manual_benchmark.json"
$startedAt = [DateTimeOffset]::UtcNow
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$steps = [System.Collections.Generic.List[object]]::new()
$excel = $null
$workbook = $null

function Add-Step {
    param(
        [string]$Action,
        [string]$Evidence
    )

    $steps.Add([pscustomobject]@{
        order = $steps.Count + 1
        action = $Action
        elapsed_ms = [Math]::Round($stopwatch.Elapsed.TotalMilliseconds, 1)
        evidence = $Evidence
    })
    Write-Host ("[{0}] {1} ({2} ms)" -f $steps.Count, $Action, $steps[-1].elapsed_ms)
}

function Set-CellValue {
    param(
        [object]$Sheet,
        [int]$Row,
        [int]$Column,
        [object]$Value
    )

    $cell = $Sheet.Cells.Item($Row, $Column)
    try {
        [void]$cell.GetType().InvokeMember(
            "Value2",
            [System.Reflection.BindingFlags]::SetProperty,
            $null,
            $cell,
            [object[]]@($Value)
        )
    }
    finally {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($cell)
    }
}

try {
    Add-Step "Launch Excel and create workbook" "Excel COM session created"
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $workbook = $excel.Workbooks.Add()

    $eventsSheet = $workbook.Worksheets.Item(1)
    $reportSheet = $workbook.Worksheets.Add()
    $notesSheet = $workbook.Worksheets.Add()
    $eventsSheet.Name = "Failure Events"
    $reportSheet.Name = "Weekly Report"
    $notesSheet.Name = "Method Notes"

    Add-Step "Create the four-event source table" "Four audited failure rows"
    $eventHeaders = @(
        "Event",
        "Start UTC",
        "End UTC",
        "Type",
        "Severity",
        "Duration h",
        "Week Start",
        "In Week",
        "Previous End UTC",
        "Gap Overlap h",
        "Maintenance Remark"
    )
    for ($column = 1; $column -le $eventHeaders.Count; $column++) {
        $eventsSheet.Cells.Item(1, $column).Value2 = $eventHeaders[$column - 1]
    }

    $events = @(
        @{
            Event = "E01"
            Start = [datetime]"2020-04-18T00:00:00"
            End = [datetime]"2020-04-18T23:59:00"
            Type = "Air Leak"
            Severity = "High Stress"
            Gap = 0.095
            Remark = ""
        },
        @{
            Event = "E02"
            Start = [datetime]"2020-05-29T23:30:00"
            End = [datetime]"2020-05-30T06:00:00"
            Type = "Air Leak"
            Severity = "High Stress"
            Gap = 0.0
            Remark = "Maintenance on 30Apr at 12:00"
        },
        @{
            Event = "E03"
            Start = [datetime]"2020-06-05T10:00:00"
            End = [datetime]"2020-06-07T14:30:00"
            Type = "Air Leak"
            Severity = "High Stress"
            Gap = 4.8205555556
            Remark = "Maintenance on 8Jun at 16:00"
        },
        @{
            Event = "E04"
            Start = [datetime]"2020-07-15T14:30:00"
            End = [datetime]"2020-07-15T19:00:00"
            Type = "Air Leak"
            Severity = "High Stress"
            Gap = 0.0358333333
            Remark = "Maintenance on 16Jul at 00:00"
        }
    )

    for ($index = 0; $index -lt $events.Count; $index++) {
        $row = $index + 2
        $eventRecord = $events[$index]
        $startOa = [double]$eventRecord.Start.ToOADate()
        $endOa = [double]$eventRecord.End.ToOADate()
        $gapHours = [double]$eventRecord.Gap
        $eventId = [string]$eventRecord.Event
        $failureType = [string]$eventRecord.Type
        $severity = [string]$eventRecord.Severity
        $remark = [string]$eventRecord.Remark
        Set-CellValue $eventsSheet $row 1 $eventId
        Set-CellValue $eventsSheet $row 2 $startOa
        Set-CellValue $eventsSheet $row 3 $endOa
        Set-CellValue $eventsSheet $row 4 $failureType
        Set-CellValue $eventsSheet $row 5 $severity
        Set-CellValue $eventsSheet $row 10 $gapHours
        Set-CellValue $eventsSheet $row 11 $remark
    }

    Add-Step "Calculate annotated duration" "End time minus start time, converted to hours"
    $eventsSheet.Range("F2:F5").Formula = "=(C2-B2)*24"
    $eventsSheet.Range("B2:C5").NumberFormat = "yyyy-mm-dd hh:mm"
    $eventsSheet.Range("F2:F5").NumberFormat = "0.000000"

    Add-Step "Derive Monday week bucket" "Formula subtracts weekday offset from start time"
    $eventsSheet.Range("G2:G5").Formula = "=B2-WEEKDAY(B2,3)"
    $eventsSheet.Range("G2:G5").NumberFormat = "yyyy-mm-dd"

    Add-Step "Set selectable report week" "2020-06-01 through 2020-06-08 UTC"
    $reportSheet.Cells.Item(1, 1).Value2 = "Weekly maintenance report"
    $reportSheet.Cells.Item(3, 1).Value2 = "Week start UTC"
    $weekStartOa = [double]([datetime]"2020-06-01T00:00:00").ToOADate()
    Set-CellValue $reportSheet 3 2 $weekStartOa
    $reportSheet.Cells.Item(4, 1).Value2 = "Week end UTC"
    $reportSheet.Cells.Item(4, 2).Formula = "=B3+7"
    $reportSheet.Range("B3:B4").NumberFormat = "yyyy-mm-dd hh:mm"

    Add-Step "Classify events into the selected week" "Start timestamp uses a half-open weekly range"
    $eventsSheet.Range("H2:H5").Formula = (
        '=IF(AND(B2>=''Weekly Report''!$B$3,B2<''Weekly Report''!$B$4),1,0)'
    )

    Add-Step "Count annotated events in the week" "COUNTIF over the in-week flag"
    $reportSheet.Cells.Item(6, 1).Value2 = "Weekly event count"
    $reportSheet.Cells.Item(6, 2).Formula = (
        '=COUNTIF(''Failure Events''!$H$2:$H$5,1)'
    )

    Add-Step "Find maximum annotated duration" "MAXIFS restricted to the selected week"
    $reportSheet.Cells.Item(7, 1).Value2 = "Longest duration h"
    $reportSheet.Cells.Item(7, 2).Formula = (
        '=MAXIFS(''Failure Events''!$F$2:$F$5,''Failure Events''!$H$2:$H$5,1)'
    )
    $reportSheet.Cells.Item(7, 2).NumberFormat = "0.0000"

    Add-Step "Identify the longest event" "INDEX/MATCH on week flag and maximum duration"
    $reportSheet.Cells.Item(8, 1).Value2 = "Longest event"
    $reportSheet.Cells.Item(8, 2).Formula = (
        '=INDEX(''Failure Events''!$A$2:$A$5,MATCH(1,INDEX(' +
        '(''Failure Events''!$H$2:$H$5=1)*(''Failure Events''!$F$2:$F$5=$B$7),0),0))'
    )

    Add-Step "Read the longest event failure type" "Lookup by event ID"
    $reportSheet.Cells.Item(9, 1).Value2 = "Longest event type"
    $reportSheet.Cells.Item(9, 2).Formula = (
        '=INDEX(''Failure Events''!$D$2:$D$5,MATCH($B$8,''Failure Events''!$A$2:$A$5,0))'
    )

    Add-Step "Aggregate weekly duration by failure type" "SUMIFS by type and week flag"
    $reportSheet.Cells.Item(10, 1).Value2 = "Highest weekly type duration h"
    $reportSheet.Cells.Item(10, 2).Formula = (
        '=SUMIFS(''Failure Events''!$F$2:$F$5,''Failure Events''!$D$2:$D$5,$B$9,' +
        '''Failure Events''!$H$2:$H$5,1)'
    )
    $reportSheet.Cells.Item(10, 2).NumberFormat = "0.0000"

    Add-Step "Read the normalized answer pair" "Both fixed questions answered from source event IDs"
    $reportSheet.Cells.Item(12, 1).Value2 = "Q1: Longest annotated failure"
    $reportSheet.Cells.Item(12, 2).Formula = '=$B$8'
    $reportSheet.Cells.Item(13, 1).Value2 = "Q1: Duration h"
    $reportSheet.Cells.Item(13, 2).Formula = '=$B$7'
    $reportSheet.Cells.Item(14, 1).Value2 = "Q2: Highest-duration type"
    $reportSheet.Cells.Item(14, 2).Formula = '=$B$9'
    $reportSheet.Cells.Item(15, 1).Value2 = "Q2: Cumulative duration h"
    $reportSheet.Cells.Item(15, 2).Formula = '=$B$10'
    $reportSheet.Range("A12:B15").Font.Bold = $true

    Add-Step "Prepare previous-event interval and gap evidence" "Source failure ordering and audited gap overlap"
    $eventsSheet.Cells.Item(2, 9).Value2 = $null
    for ($row = 3; $row -le 5; $row++) {
        $eventsSheet.Cells.Item($row, 9).Formula = "=C" + ($row - 1)
    }
    $eventsSheet.Range("I2:I5").NumberFormat = "yyyy-mm-dd hh:mm"
    $eventsSheet.Range("J2:J5").NumberFormat = "0.000000"

    Add-Step "Add method and limitation notes" "Same-week, event-level n=1 comparison"
    $notesSheet.Cells.Item(1, 1).Value2 = "Method"
    $notesSheet.Cells.Item(2, 1).Value2 = (
        "Instrumented Excel formula workflow for the fixed week 2020-06-01 to 2020-06-08 UTC."
    )
    $notesSheet.Cells.Item(3, 1).Value2 = (
        "Durations use end minus start. Weekly rows use start timestamps in a half-open interval."
    )
    $notesSheet.Cells.Item(4, 1).Value2 = (
        "This is a personal n=1 self-experiment, not a user study or a measured business benefit."
    )
    $notesSheet.Cells.Item(5, 1).Value2 = (
        "Excel operation timing excludes human interpretation and learning time."
    )

    Add-Step "Calculate workbook and save evidence" $workbookPath
    $excel.CalculateFull()
    if (Test-Path $workbookPath) {
        Remove-Item -LiteralPath $workbookPath -Force
    }
    $workbook.SaveAs($workbookPath, 51)

    $answers = [pscustomobject]@{
        weekly_event_count = [int]$reportSheet.Cells.Item(6, 2).Value2
        longest_event_id = [string]$reportSheet.Cells.Item(8, 2).Value2
        longest_duration_hours = [double]$reportSheet.Cells.Item(7, 2).Value2
        highest_duration_type = [string]$reportSheet.Cells.Item(9, 2).Value2
        highest_type_duration_hours = [double]$reportSheet.Cells.Item(10, 2).Value2
    }
    Add-Step "Capture normalized answers" "Weekly answers read from formula cells"

    $stopwatch.Stop()
    $completedAt = [DateTimeOffset]::UtcNow
    $result = [pscustomobject]@{
        experiment = "personal_n_1_instrumented_excel_self_experiment"
        disclosure = (
            "This is not a user study. It measures one scripted spreadsheet workflow and " +
            "does not estimate a population-level time saving."
        )
        week_started_at_utc = "2020-06-01T00:00:00Z"
        week_ended_at_utc = "2020-06-08T00:00:00Z"
        tool = "Microsoft Excel 16.0 COM automation"
        started_at_utc = $startedAt.ToString("o")
        completed_at_utc = $completedAt.ToString("o")
        elapsed_seconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
        operation_count = $steps.Count
        answers = $answers
        traceable_to_source_events = $true
        traceability_note = (
            "The workbook retains event IDs, source report timestamps, and maintenance remarks, " +
            "but it does not independently reconstruct all raw telemetry gaps."
        )
        steps = $steps
        workbook = $workbookPath
    }

    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding utf8
    $result | ConvertTo-Json -Depth 8
}
finally {
    $stopwatch.Stop()
    if ($null -ne $workbook) {
        $workbook.Close($false)
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
    }
    if ($null -ne $excel) {
        $excel.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
