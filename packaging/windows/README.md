# Windows auto-start

For the MVP, use Windows Task Scheduler rather than running TashevNet as an elevated service.

Recommended task:
- Trigger: **At log on**.
- Action: start `C:\path\to\tashevnet\.venv\Scripts\tashevnet.exe`.
- Arguments: `--config C:\path\to\tashevnet\config.yaml run`.
- Start in: the repository directory.
- Run with the normal user account unless a specific recovery command truly requires more privileges.

A native tray application and installer are tracked in the roadmap.
