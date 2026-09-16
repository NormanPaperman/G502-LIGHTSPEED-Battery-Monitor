# 🖱️ G502 LIGHTSPEED Battery Monitor

A lightweight Windows system-tray battery monitor for the **Logitech G502 LIGHTSPEED wireless mouse**.

This utility lets you see your mouse battery level without needing to keep Logitech G HUB open.

## Features

* 🔋 Displays the current mouse battery percentage
* 🖱️ Designed specifically for the Logitech G502 LIGHTSPEED
* 🖥️ Runs quietly in the Windows system tray
* 🔄 Automatically updates the battery level
* ⚡ Uses the Logitech wireless receiver
* 🚫 Does not require Logitech G HUB to remain open
* 🟢 Displays `F` when the battery reaches 100%
* ⚠️ Low-battery warning
* 🪶 Lightweight and designed to run in the background

## Download

The easiest way to use the program is to download the latest Windows executable from the **Releases** section of this repository.

### Windows executable

**G502_Battery.exe**

Download it from:

**Releases → Latest Release → G502_Battery.exe**

No Python installation is required when using the compiled `.exe`.

## How to Use

1. Download `G502_Battery.exe` from the latest Release.
2. Make sure your G502 LIGHTSPEED wireless receiver is connected.
3. Run `G502_Battery.exe`.
4. The battery percentage will appear in the Windows system tray.

The program runs in the background and periodically updates the displayed battery level.

## Start Automatically With Windows

If you want the battery monitor to start automatically when Windows starts:

1. Press **Win + R**
2. Enter:

```text
shell:startup
```

3. Press **Enter**.
4. Create a shortcut to `G502_Battery.exe`.
5. Place the shortcut in the Startup folder.

Windows will then start the battery monitor automatically when you log in.

## Supported Hardware

Currently developed and tested with:

* **Logitech G502 LIGHTSPEED**

Other Logitech mice may use different HID/HID++ communication and are not guaranteed to work.

## How It Works

The application communicates with the Logitech wireless receiver using HID/HID++ communication to retrieve the mouse battery information.

It is intended as a lightweight battery-monitoring utility for users who want to see their mouse battery level without keeping Logitech G HUB running.

## Source Code

The Python source code is included in this repository.

You can inspect, modify, or build the application yourself.

## Windows SmartScreen / Antivirus Warnings

Because the executable is independently compiled and is not digitally code-signed, Windows SmartScreen or antivirus software may occasionally display a warning when downloading or running the program.

If Windows displays a warning, make sure you downloaded the executable from this repository's official GitHub Release before choosing to run it.

## Disclaimer

This is an independent community project and is **not affiliated with, endorsed by, or sponsored by Logitech**.

Logitech, G502 LIGHTSPEED, and G HUB are trademarks of Logitech.

Use this software at your own discretion.

## License

This project is released under the **MIT License**.

See the `LICENSE` file for details.
