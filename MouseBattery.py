import hid
import time
import threading
import ctypes
import tkinter as tk
import pystray


from PIL import Image, ImageDraw, ImageFont

# ============================================================
# LOGITECH HID++ DISCOVERY
# ============================================================

VID = 0x046D
RECEIVER_PID = 0xC539

USAGE_PAGE = 0xFF00
USAGE = 0x0002

REPORT_ID = 0x11
DEVICE_INDEX = 0x01
SOFTWARE_ID = 0x01



# HID++ feature IDs
ROOT_FEATURE = 0x0000
DEVICE_NAME_FEATURE = 0x0005

BATTERY_FEATURES = {
    0x1004: "Unified Battery",
    0x1000: "Battery Status",
    0x1001: "Battery Voltage",
}


# ============================================================
# FIND LOGITECH LIGHTSPEED RECEIVER
# ============================================================

def find_receiver():

    devices = hid.enumerate(
        VID,
        RECEIVER_PID
    )

    for device in devices:

        if (
            device.get("usage_page") == USAGE_PAGE
            and device.get("usage") == USAGE
        ):
            return device

    return None


# ============================================================
# SEND HID++ LONG REPORT
# ============================================================

def send_request(
    device,
    feature_index,
    function,
    params=None
):

    if params is None:
        params = []

    request = [
        REPORT_ID,
        DEVICE_INDEX,
        feature_index,
        function,
    ]

    request.extend(params)

    request.extend(
        [0x00] * (20 - len(request))
    )

    result = device.write(request)

    if result < 0:
        return None

    # --------------------------------------------------------
    # Wait for the response belonging to THIS request.
    #
    # The Logitech receiver can also deliver unrelated
    # HID++ traffic while we are waiting.
    # --------------------------------------------------------

    deadline = time.time() + 1.0

    while time.time() < deadline:

        remaining = max(
            1,
            int(
                (deadline - time.time()) * 1000
            )
        )

        response = device.read(
            20,
            remaining
        )

        if not response:
            continue

        # Ignore anything that isn't our HID++ report.
        if len(response) < 4:
            continue

        # Wrong report ID.
        if response[0] != REPORT_ID:
            continue

        # Wrong device slot.
        if response[1] != DEVICE_INDEX:
            continue

        # Wrong feature.
        if response[2] != feature_index:
            continue

        # Normal response should have the same function.
        #
        # HID++ errors/notifications can use other function
        # values, so don't accept those as our battery data.
        if response[3] != function:
            continue

        return response

    return None

# ============================================================
# DISCOVER FEATURE INDEX
# ============================================================

def discover_feature(device, feature_id):

    response = send_request(
        device,
        ROOT_FEATURE,
        SOFTWARE_ID,
        [
            (feature_id >> 8) & 0xFF,
            feature_id & 0xFF,
        ]
    )

    if not response or len(response) < 7:
        return None

    feature_index = response[4]

    if feature_index == 0:
        return None

    return {
        "index": feature_index,
        "type": response[5],
        "version": response[6],
    }


# ============================================================
# DISCOVER DEVICE NAME
# ============================================================

def get_device_name(device):

    feature = discover_feature(
        device,
        DEVICE_NAME_FEATURE
    )

    if not feature:
        return None

    feature_index = feature["index"]

    # --------------------------------------------------------
    # Get total name length
    # --------------------------------------------------------

    response = send_request(
        device,
        feature_index,
        0x00
    )

    if not response or len(response) < 5:
        return None

    name_length = response[4]

    print(
        f"  Device name length: {name_length} bytes"
    )

    # --------------------------------------------------------
    # Read name in 16-byte chunks
    # --------------------------------------------------------

    name_bytes = bytearray()

    offset = 0

    while offset < name_length:

        response = send_request(
            device,
            feature_index,
            0x10,
            [offset]
        )

        if not response or len(response) < 5:
            break

        remaining = name_length - offset

        chunk_size = min(
            16,
            remaining
        )

        chunk = response[4:4 + chunk_size]

        name_bytes.extend(chunk)

        print(
            f"  Name chunk {offset:02d}: "
            f"{bytes(chunk)!r}"
        )

        offset += chunk_size

    if len(name_bytes) != name_length:

        print(
            f"  WARNING: Expected {name_length} bytes, "
            f"received {len(name_bytes)}"
        )

    try:

        return name_bytes.decode(
            "utf-8",
            errors="replace"
        ).rstrip("\x00")

    except Exception:

        return None


# ============================================================
# DISCOVER BATTERY
# ============================================================

def discover_battery(device):

    print()
    print("Battery feature discovery:")
    print()

    supported = []

    for feature_id, name in BATTERY_FEATURES.items():

        feature = discover_feature(
            device,
            feature_id
        )

        if feature:

            print(
                f"  {name}: SUPPORTED"
            )

            print(
                f"    Feature ID:    "
                f"0x{feature_id:04X}"
            )

            print(
                f"    Runtime index: "
                f"0x{feature['index']:02X}"
            )

            print(
                f"    Version:       "
                f"{feature['version']}"
            )

            supported.append(
                (
                    feature_id,
                    name,
                    feature
                )
            )

        else:

            print(
                f"  {name}: NOT SUPPORTED"
            )

    return supported


# ============================================================
# READ BATTERY VOLTAGE
# ============================================================

def read_battery_voltage(
    device,
    feature_index
):

    response = send_request(
        device,
        feature_index,
        0x00
    )

    if not response or len(response) < 6:

        print(
            "  Battery response: NONE"
        )

        return None

    print(
        "  Raw battery response:",
        " ".join(
            f"{byte:02X}"
            for byte in response
        )
    )

    voltage = (
    (response[4] << 8)
    | response[5]
    )

    # Ignore obviously invalid/transient readings.
    if voltage < 3000:
        print(
            f"  Ignoring invalid voltage: "
            f"{voltage} mV"
        )
        return None

    return voltage

def voltage_to_percent(voltage):

    # G502 LIGHTSPEED calibration.
    #
    # Temporary curve based on the known G502 reading:
    # 4069 mV = 90% according to G HUB.
    #
    # This is ONLY used when the detected mouse is
    # positively identified as a G502 LIGHTSPEED.

    curve = [
        (4200, 100),
        (4150, 98),
        (4120, 95),
        (4100, 93),
        (4080, 91),
        (4069, 90),
        (4050, 88),
        (4030, 85),
        (4005, 82),
        (4003, 82),
        (4000, 81),
        (3990, 79),
        (3984, 79),
        (3981, 79), 
        (3974, 78),
        (3973, 77),
        (3969, 77),
        (3968, 76),
        (3963, 76),
        (3961, 75),
        (3959, 75),
        (3957, 75),
        (3955, 75),
        (3950, 74),
        (3938, 71),
        (3929, 71),
        (3928, 71),
        (3913, 69),
        (3911, 68),
        (3910, 68),
        (3888, 65),
        (3865, 61),
        (3858, 59),
        (3846, 56),
        (3843, 55),
        (3832, 55),
        (3831, 49),
        (3822, 49),
        (3802, 48),
        (3800, 47),
        (3798, 43),
        (3794, 39),
        (3790, 39),
        (3788, 39),
        (3785, 39),
        (3776, 38),
        (3774, 34),
        (3773, 34),
        (3766, 32),
        (3765, 32),
        (3764, 32),
        (3757, 32),
        (3753, 31),
        (3750, 30),
        (3746, 28),
        (3744, 28),
        (3736, 26),
        (3735, 22),
        (3731, 19),
        (3728, 19),
        (3722, 19),
        (3716, 17),
        (3710, 17),
        (3708, 17),
        (3704, 17),
        (3700, 15),
        (3650, 8),
        (3600, 5),
        (3500, 0),
    ]

    if voltage >= curve[0][0]:
        return 100

    if voltage <= curve[-1][0]:
        return 0

    for i in range(len(curve) - 1):

        high_voltage, high_percent = curve[i]
        low_voltage, low_percent = curve[i + 1]

        if low_voltage <= voltage <= high_voltage:

            percent = (
                high_percent
                + (
                    (voltage - high_voltage)
                    / (low_voltage - high_voltage)
                )
                * (low_percent - high_percent)
            )

            return round(percent)

    return 0
class SecondMonitorDisplay:

    def __init__(self):

        self.enabled = False

        self.root = tk.Tk()

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        # Transparent background color.
        self.root.configure(
            bg="black"
        )

        try:
            self.root.attributes(
                "-transparentcolor",
                "black"
            )
        except Exception:
            pass

        self.label = tk.Label(
            self.root,
            text="?",
            font=(
                "Segoe UI",
                15,
                "bold"
            ),
            fg="white",
            bg="black"
        )

        self.label.pack()

        # ----------------------------------------------------
        # Only enable the display if a second monitor exists.
        # ----------------------------------------------------

        if self.position_on_second_monitor():

            self.enabled = True
            self.root.deiconify()

        else:

            self.root.withdraw()

    def position_on_second_monitor(self):

        user32 = ctypes.windll.user32

        monitors = []

        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_long * 4),
            ctypes.c_void_p
        )

        def callback(
            hmonitor,
            hdc,
            rect,
            data
        ):

            r = rect.contents

            monitors.append(
                (
                    int(r[0]),
                    int(r[1]),
                    int(r[2]),
                    int(r[3])
                )
            )

            return 1

        user32.EnumDisplayMonitors(
            None,
            None,
            MONITORENUMPROC(callback),
            0
        )

        if len(monitors) < 2:

            print(
                "[Second Monitor] "
                "Only one monitor detected. "
                "Second-monitor display disabled."
            )

            return False

        # Second monitor
        left, top, right, bottom = monitors[1]

        # Size of the display window
        window_width = 70
        window_height = 35

        # Position near bottom-right,
        # above the Windows clock.
        x = right - window_width - 20
        y = bottom - window_height - 75

        self.root.geometry(
            f"{window_width}x{window_height}"
            f"+{x}+{y}"
        )

        print(
            "[Second Monitor] "
            "Second monitor detected. "
            "Battery number enabled."
        )

        return True

    def update(self, percent):

        if not self.enabled:
            return

        if percent is None:

            text = "?"
            fill = "white"

        else:

            text = str(percent)

            if percent > 50:
                fill = "green"

            elif percent > 20:
                fill = "yellow"

            else:
                fill = "red"

        self.label.config(
            text=text,
            fg=fill
        )

        self.root.deiconify()

        self.root.update_idletasks()
        self.root.update()

    def close(self):

        try:

            self.root.destroy()

        except Exception:

            pass
class BatteryTray:

    def __init__(self, mouse_name):

        self.mouse_name = mouse_name
        self.voltage = None
        self.percent = None

        self.icon = pystray.Icon(
            "MouseBattery"
        )
        self.warning_phase = False
        self.warning_thread = None
        self.show_mouse = False
        self.update_icon()
    def warning_loop(self):

        while True:

            # --------------------------------------------------------
            # NORMAL BATTERY
            # --------------------------------------------------------
            # Above 20%, alternate:
            # percentage -> mouse -> percentage -> mouse

            if self.percent is None or self.percent > 20:

                self.show_mouse = not self.show_mouse

            # --------------------------------------------------------
            # LOW BATTERY
            # --------------------------------------------------------
            # At 20% or below, alternate:
            # percentage -> lightning -> percentage -> lightning

            else:

                self.warning_phase = not self.warning_phase

            self.update_icon()

            time.sleep(5)
    def update_icon(self):

        size = 64

        image = Image.new(
            "RGBA",
            (size, size),
            (0, 0, 0, 0)
        )

        draw = ImageDraw.Draw(image)

        # --------------------------------------------------------
        # DETERMINE WHAT TO DISPLAY
        # --------------------------------------------------------

        draw_mouse = False

        if self.percent is None:

            text = "?"

          

        elif self.percent == 100:

            # Fully charged:
            # Display F instead of 100 so it fits
            # cleanly inside the tray icon.
            text = "F"

        elif self.percent <= 20:

            # Low battery:
            # percentage <-> lightning bolt
            if self.warning_phase:
                text = "⚡"
            else:
                text = str(self.percent)

        elif self.show_mouse:

            # Normal battery:
            # percentage <-> simple mouse
            text = None
            draw_mouse = True

        else:

            text = str(self.percent)

        # --------------------------------------------------------
        # COLOR
        # --------------------------------------------------------

        if self.percent is None:

            fill = "white"

        elif self.percent > 50:

            fill = "green"

        elif self.percent > 20:

            fill = "yellow"

        else:

            fill = "red"

                # --------------------------------------------------------
        # DRAW SIMPLE MOUSE
        # --------------------------------------------------------

        if draw_mouse:

            # ----------------------------------------------------
            # MOUSE SIZE
            #
            # Sized to visually match the 50px Segoe UI Emoji
            # used by the PRO X 2 headset icon.
            # ----------------------------------------------------

            # ----------------------------------------------------
            # EARS
            # ----------------------------------------------------

            draw.ellipse(
                (6, 1, 31, 29),
                fill="gray",
                outline="black",
                width=2
            )

            draw.ellipse(
                (33, 1, 58, 29),
                fill="gray",
                outline="black",
                width=2
            )

            # ----------------------------------------------------
            # HEAD
            # ----------------------------------------------------

            draw.ellipse(
                (7, 13, 57, 61),
                fill="gray",
                outline="black",
                width=2
            )

            # ----------------------------------------------------
            # EYES
            # ----------------------------------------------------

            draw.ellipse(
                (20, 30, 25, 35),
                fill="black"
            )

            draw.ellipse(
                (39, 30, 44, 35),
                fill="black"
            )
            # ----------------------------------------------------
            # NOSE
            # ----------------------------------------------------

            draw.ellipse(
                (30, 37, 34, 41),
                fill="black"
            )

            # ----------------------------------------------------
            # MOUTH
            # ----------------------------------------------------

            draw.arc(
                (26, 38, 32, 46),
                0,
                90,
                fill="black",
                width=1
            )

            draw.arc(
                (32, 38, 38, 46),
                90,
                180,
                fill="black",
                width=1
            )
            # ----------------------------------------------------
            # WHISKERS
            # ----------------------------------------------------

            # Left whiskers
            draw.line(
                (20, 39, 4, 35),
                fill="black",
                width=2
            )

            draw.line(
                (20, 42, 3, 42),
                fill="black",
                width=2
            )

            draw.line(
                (20, 45, 4, 49),
                fill="black",
                width=2
            )

            # Right whiskers
            draw.line(
                (44, 39, 60, 35),
                fill="black",
                width=2
            )

            draw.line(
                (44, 42, 61, 42),
                fill="black",
                width=2
            )

            draw.line(
                (44, 45, 60, 49),
                fill="black",
                width=2
            )
        # --------------------------------------------------------
        # DRAW TEXT / LIGHTNING
        # --------------------------------------------------------

        else:

            # ----------------------------------------------------
            # LOW BATTERY LIGHTNING BOLT
            # ----------------------------------------------------

            if text == "⚡":

                points = [
                    (37, 3),
                    (14, 31),
                    (27, 31),
                    (20, 61),
                    (50, 25),
                    (36, 25),
                ]

                # Black shadow / outline
                shadow_points = [
                    (38, 4),
                    (15, 32),
                    (28, 32),
                    (21, 62),
                    (51, 26),
                    (37, 26),
                ]

                draw.polygon(
                    shadow_points,
                    fill="black"
                )

                draw.polygon(
                    points,
                    fill=fill
                )

            # ----------------------------------------------------
            # NORMAL BATTERY PERCENTAGE
            # ----------------------------------------------------

            else:

                try:

                    font = ImageFont.truetype(
                        "C:/Windows/Fonts/segoeuib.ttf",
                        60
                    )

                except Exception:

                    font = ImageFont.load_default()

                bbox = draw.textbbox(
                    (0, 0),
                    text,
                    font=font
                )

                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                padding_x = 15
                available_width = size - (padding_x * 2)

                x = padding_x + (
                    (available_width - text_width) // 2
                )

                y = (
                    (size - text_height) // 2
                ) - 25

                draw.text(
                    (x + 1, y + 1),
                    text,
                    font=font,
                    fill="black"
                )

                draw.text(
                    (x, y),
                    text,
                    font=font,
                    fill=fill
                )

        # --------------------------------------------------------
        # UPDATE TRAY ICON
        # --------------------------------------------------------

        # --------------------------------------------------------
        # UPDATE TRAY ICON
        # --------------------------------------------------------

        self.icon.icon = image

        # --------------------------------------------------------
        # TOOLTIP
        # --------------------------------------------------------

        if self.percent is not None:

            self.icon.title = (
                f"{self.mouse_name}\n"
                f"Battery: {self.percent}%\n"
                f"Voltage: {self.voltage} mV"
            )

        else:

            self.icon.title = (
                f"{self.mouse_name}\n"
                f"Voltage: {self.voltage} mV"
            )
    def update(self, voltage):

        self.voltage = voltage

        # Only use the percentage curve for
        # the G502 LIGHTSPEED.
        if (
            self.mouse_name
            == "G502 LIGHTSPEED Wireless Gaming Mouse"
        ):

            self.percent = voltage_to_percent(
                voltage
            )

        else:

            self.percent = None

        self.update_icon()

    def run(self):

        menu = pystray.Menu(
            pystray.MenuItem(
                "Refresh Now",
                self.refresh
            ),
            pystray.MenuItem(
                "Exit",
                self.exit
            )
        )

        self.icon.menu = menu

        # Start the independent 1-second warning animation.
        self.warning_thread = threading.Thread(
            target=self.warning_loop,
            daemon=True
        )

        self.warning_thread.start()

        self.icon.run()

    def refresh(self, icon=None, item=None):

        pass

    def exit(self, icon=None, item=None):

        self.icon.stop()

def draw_lightning_bolt(
    image,
    fill
):

    draw = ImageDraw.Draw(image)

    # --------------------------------------------------------
    # LARGE CENTERED LIGHTNING BOLT
    # Sized specifically for the 64x64 tray icon.
    # --------------------------------------------------------

    points = [
        (37, 3),
        (14, 31),
        (27, 31),
        (20, 61),
        (50, 25),
        (36, 25),
    ]

    draw.polygon(
        points,
        fill=fill
    )

# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("LOGITECH MOUSE AUTO DISCOVERY")
    print("=" * 60)

    # --------------------------------------------------------
    # Receiver
    # --------------------------------------------------------

    receiver = find_receiver()

    if not receiver:

        print()
        print(
            "ERROR: Logitech C539 receiver not found."
        )

        return

    print()
    print("Receiver detected:")
    print(
        f"  Product: "
        f"{receiver.get('product_string')}"
    )

    print(
        f"  VID: "
        f"0x{receiver['vendor_id']:04X}"
    )

    print(
        f"  PID: "
        f"0x{receiver['product_id']:04X}"
    )

    device = hid.device()

    try:

        device.open_path(
            receiver["path"]
        )

        print()
        print("Receiver opened.")

        # ----------------------------------------------------
        # Identify mouse
        # ----------------------------------------------------

        print()
        print("Identifying mouse...")

        mouse_name = get_device_name(
            device
        )

        if mouse_name:

            print(
                f"  Mouse: {mouse_name}"
            )

        else:

            print(
                "  Mouse name could not be determined."
            )

        # ----------------------------------------------------
        # Battery features
        # ----------------------------------------------------

        supported = discover_battery(
            device
        )

        # ----------------------------------------------------
        # Select battery voltage
        # ----------------------------------------------------

        voltage_feature = None

        for feature_id, name, feature in supported:

            if feature_id == 0x1001:

                voltage_feature = feature
                break

        if voltage_feature:

            voltage = read_battery_voltage(
                device,
                voltage_feature["index"]
            )

            print()

            if voltage is not None:

                print(
                    f"Battery voltage: "
                    f"{voltage} mV"
                )

            else:

                print(
                    "Battery voltage could not be read."
                )

        else:

            print()
            print(
                "No supported battery-voltage "
                "feature found."
            )

        print()
        print("=" * 60)
        print("DISCOVERY COMPLETE")
        print("=" * 60)

        # ----------------------------------------------------
        # Windows tray monitor
        # ----------------------------------------------------

        tray = BatteryTray(
            mouse_name
        )

        # ----------------------------------------------------
        # AUTOMATIC SECOND-MONITOR DETECTION
        # ----------------------------------------------------
        # If a second monitor exists, show the battery
        # percentage there.
        #
        # If only one monitor exists, the display is
        # automatically disabled.
        # ----------------------------------------------------

        second_display = SecondMonitorDisplay()

        if second_display.enabled:

            second_display.update(
                tray.percent
            )

        # ----------------------------------------------------
        # START TRAY MONITOR
        # ----------------------------------------------------

        tray_thread = threading.Thread(
            target=tray.run,
            daemon=True
        )

        tray_thread.start()

        time.sleep(1)

        print()
        print("=" * 60)
        print("TRAY MONITOR")
        print(
            "Mouse battery is now shown in the"
        )
        print(
            "Windows system tray."
        )

        if second_display.enabled:

            print(
                "Second-monitor battery display is enabled."
            )

        else:

            print(
                "No second monitor detected."
            )

        print(
            "Press Ctrl+C to stop."
        )
        print("=" * 60)

        while True:

            voltage = read_battery_voltage(
                device,
                voltage_feature["index"]
            )

            if voltage is not None:

                tray.update(
                    voltage
                )

                if second_display.enabled:

                    second_display.update(
                        tray.percent
                    )

                if tray.percent is not None:

                    print(
                        f"Battery: "
                        f"{voltage} mV "
                        f"({tray.percent}%)"
                    )

                else:

                    print(
                        f"Battery: "
                        f"{voltage} mV"
                    )

            else:

                print(
                    "Battery voltage read failed."
                )

            time.sleep(5)    

        else:

            print()
            print(
                "Tray monitor not started because "
                "no supported battery feature was found."
            )

    except KeyboardInterrupt:

        print()
        print(
            "Voltage monitor stopped."
        )

    except Exception as error:

        print()
        print(
            f"ERROR: {error}"
        )

    finally:

        try:

            device.close()

        except Exception:

            pass


if __name__ == "__main__":
    main()