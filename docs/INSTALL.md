# Installing Backtester

## Windows
1. Download `backtester-<ver>-windows-x64.exe` from the [Releases page](https://github.com/backtester/backtester/releases/latest).
2. Run it. SmartScreen may warn that the publisher is unknown — click **More info** → **Run anyway**. The binary is unsigned (see Roadmap).
3. The installer adds a Start-menu and Desktop shortcut.
4. Launch **Backtester** — a tray icon appears and your default browser opens to the app.

### Portable Windows
Download `backtester-<ver>-windows-x64.zip`, extract, and run `Backtester.exe`. Create a file named `portable.txt` next to the executable to make all data live in `./data/` instead of `%APPDATA%`.

## macOS
Download `Backtester-<ver>.dmg`, drag to Applications, double-click. On first launch right-click → **Open** to bypass Gatekeeper (the app is unsigned).

## Linux
- AppImage: `chmod +x Backtester-<ver>-x86_64.AppImage && ./Backtester-<ver>-x86_64.AppImage`
- Debian/Ubuntu: `sudo dpkg -i backtester_<ver>_amd64.deb && backtester`

## Where is my data?
| OS | Path |
|---|---|
| Windows | `%APPDATA%\Backtester\` |
| macOS | `~/Library/Application Support/Backtester/` |
| Linux | `$XDG_DATA_HOME/Backtester/` (default `~/.local/share/Backtester/`) |

The tray menu's **Open data folder** opens this directly.

## Updating
The app shows a banner when a new version is on GitHub. Download and run the new installer — your data is preserved.
