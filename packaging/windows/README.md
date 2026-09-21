# Windows auto-start

Run TashevNet with Task Scheduler under your normal account; it does not need
administrator rights for monitoring.

From the repository folder, in PowerShell:

```powershell
$action = New-ScheduledTaskAction `
  -Execute "$PWD\.venv\Scripts\tashevnet.exe" `
  -Argument "--config `"$PWD\config.yaml`" run" `
  -WorkingDirectory $PWD
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "TashevNet" -Action $action -Trigger $trigger `
  -Description "TashevNet network flight recorder"
```

Start it now with `Start-ScheduledTask TashevNet`, remove it with
`Unregister-ScheduledTask TashevNet`.

Windows support is new in 0.1.1 and has not been tested on a real machine yet: route and
adapter detection use PowerShell (`Find-NetRoute`, `Get-NetAdapter`), and ping output is
read in any language. Reports are welcome in the issue tracker.
