# Terminal MOTD (Message of the Day) Dashboard

A beautiful, high-contrast, dynamic developer dashboard for Windows terminal shells (PowerShell, CMD, Bash). It launches instantly whenever you open a new shell, providing you with a high-level view of your system resources, local weather, sandbox Git repositories status, and a task checklist.

---

## Features
- 🖥️ **System Health Monitor**: Live percentages and progress bars for CPU load, RAM usage, and Disk space, plus system uptime.
- ⛅ **Dynamic Weather**: Local weather info sourced directly from wttr.in.
- 🗃️ **Git Repository Tracker**: Automatically scans all project directories inside your `sandbox` folder and alerts you if there are dirty working directories, untracked changes, or if local branches are ahead/behind their GitHub remotes.
- 📝 **Productivity Todo checklist**: A lightweight, file-backed todo manager right in your terminal.
- ⚡ **Background Caching**: Weather fetching and Git status check are executed in a silent background process and cached, guaranteeing a terminal startup delay of under 50ms.
- 🎨 **Visual Themes**: Switch between `ocean` (cyan/blue) and `forest` (green/yellow) styling.

---

## Installation

### Automatic Profile Integration (PowerShell)
To make the dashboard launch automatically every time you open a terminal:
1. Open a PowerShell terminal.
2. Navigate to this directory:
   ```powershell
   cd c:\Users\lhcoy\OneDrive\Desktop\sandbox\motd
   ```
3. Run the installer script:
   ```powershell
   .\install.ps1
   ```
   This will safely create and add a hook block inside your PowerShell and PowerShell Core (`pwsh`) startup profile scripts.

### Uninstallation
To disable the automatic launch:
```powershell
.\install.ps1 -Uninstall
```
This cleanly removes the hook from all PowerShell profile files.

---

## Command Reference

### Display the Dashboard
Running the script without arguments prints the dashboard layout:
```bash
python main.py
```
*(If the background cache is older than 15 minutes, it automatically launches a silent background worker to refresh it).*

### Force Cache Refresh
To manually update cached weather and Git repository info:
```bash
python main.py --update
```

### Manage the Todo Checklist
The MOTD integrates a persistent todo checklist. You can manage it with these flags:

- **Add a Task**:
  ```bash
  python main.py --todo add "Work on Asteroids game telemetry"
  ```
- **List All Tasks**:
  ```bash
  python main.py --todo list
  ```
- **Toggle Task Completion** (Mark done or undo):
  ```bash
  python main.py --todo check <index>
  # Example: python main.py --todo check 1
  ```
- **Delete a Task**:
  ```bash
  python main.py --todo delete <index>
  ```
- **Clear All Completed Tasks**:
  ```bash
  python main.py --todo clear
  ```

---

## Configuration

Customize the tool by editing `config.json`:
- `username`: The greeting name shown at the top left.
- `weather_location`: City or region for weather queries (e.g. `Portland,ME` or `New York`).
- `theme`: Graphic color palette (`ocean`, `forest`, or default purple).
- `sections`: Toggles (`true`/`false`) for showing specific modules on the dashboard.

Example `config.json`:
```json
{
    "username": "Louie",
    "weather_location": "Portland,ME",
    "theme": "ocean",
    "sections": {
        "system_stats": true,
        "weather": true,
        "git_status": true,
        "todos": true,
        "dev_tips": true
    }
}
```
