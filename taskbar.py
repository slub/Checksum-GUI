"""Optional taskbar progress for Windows, Cinnamon/X11 and GNOME docks."""

import ctypes
import os
import shutil
import subprocess
import sys
from uuid import UUID


class TaskbarProgress:
    def __init__(self, window):
        self.window = window
        self.state = 0
        self.completed = 0
        self.total = 1
        self._interface = ctypes.c_void_p()
        self._initialized = False
        self._ready = False
        self._message = 0
        self._linux = None
        if sys.platform == "linux":
            self._linux = linux_backend(window)
        if sys.platform == "win32":
            from ctypes import wintypes

            self._msg_type = wintypes.MSG
            self._ole = ctypes.OleDLL("ole32")
            self._ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            self._ole.CoInitializeEx.restype = ctypes.c_long
            self._ole.CoCreateInstance.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
            ]
            self._ole.CoCreateInstance.restype = ctypes.c_long
            self._ole.CoUninitialize.argtypes = []
            self._ole.CoUninitialize.restype = None
            user32 = ctypes.WinDLL("user32")
            user32.RegisterWindowMessageW.argtypes = [ctypes.c_wchar_p]
            user32.RegisterWindowMessageW.restype = ctypes.c_uint
            self._message = user32.RegisterWindowMessageW("TaskbarButtonCreated")

    def _call(self, index, argtypes=(), *args):
        # IUnknown (0–2), ITaskbarList (3–7), ITaskbarList2 (8),
        # ITaskbarList3.SetProgressValue (9) and SetProgressState (10).
        table = ctypes.cast(
            self._interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents
        method = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])
        return method(self._interface, *args)

    def native_event(self, message):
        if not self._message:
            return
        msg = self._msg_type.from_address(int(message))
        if msg.message != self._message:
            return
        if not self._interface:
            try:
                self._ole.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
                self._initialized = True
                clsid = ctypes.create_string_buffer(UUID("56fdf344-fd6d-11d0-958a-006097c9a090").bytes_le)
                # IID_ITaskbarList3 from the Windows SDK's ShObjIdl_core.h.
                iid = ctypes.create_string_buffer(UUID("ea1afb91-9e28-4b86-90e9-9e9f8a5eefaf").bytes_le)
                self._ole.CoCreateInstance(clsid, None, 1, iid, ctypes.byref(self._interface))
                if self._call(3) < 0:  # HrInit
                    self.close()
                    return
            except OSError:
                self.close()
                return
        self._ready = True
        self._apply()

    def update(self, completed=0, total=1, *, active=False):
        self.state = (1 if total == 0 else 2) if active else 0
        self.completed = completed
        self.total = max(total, 1)
        if self._linux is not None:
            self._linux.update(self.state, self.completed / self.total)
        self._apply()

    def _apply(self):
        if not self._ready:
            return
        hwnd = int(self.window.winId())
        self._call(10, (ctypes.c_void_p, ctypes.c_uint), hwnd, self.state)
        if self.state == 2:
            self._call(9, (ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_ulonglong),
                       hwnd, max(0, self.completed), self.total)

    def close(self):
        if self._linux is not None:
            self._linux.update(0, 0.0)
            self._linux = None
        self._ready = False
        if self._interface:
            self._call(2)  # IUnknown.Release
            self._interface = ctypes.c_void_p()
        if self._initialized:
            self._ole.CoUninitialize()
            self._initialized = False


def linux_backend(window):
    # Prefer the actual desktop over session names, which can be customized.
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION", "")
    desktops = set(desktop.lower().split(":"))
    from PyQt6.QtGui import QGuiApplication

    platform = QGuiApplication.platformName()
    if platform not in ("xcb", "wayland", "wayland-egl"):
        return None
    if desktops & {"cinnamon", "x-cinnamon"}:
        executable = shutil.which("xprop") if platform == "xcb" else None
        return CinnamonProgress(window, executable) if executable else None
    if "gnome" in desktops or "gnome-classic" in desktops:
        try:
            return GnomeProgress()
        except (ImportError, RuntimeError):
            return None
    return None


class CinnamonProgress:
    """Publish XApp window properties understood by Cinnamon's window lists."""

    def __init__(self, window, executable):
        self.window = window
        self.executable = executable
        self._last = None

    def update(self, state, fraction):
        if not self.executable:
            return
        progress = round(min(1.0, max(0.0, fraction)) * 100) if state == 2 else 0
        values = (progress, int(state == 1))
        if values == self._last:
            return
        # Do not create a native window while MainWindow is being initialized.
        if not self.window.isVisible() and self._last is None:
            return
        try:
            for name, value in zip(
                ("_NET_WM_XAPP_PROGRESS", "_NET_WM_XAPP_PROGRESS_PULSE"), values
            ):
                subprocess.run([
                    self.executable, "-id", str(int(self.window.winId())),
                    "-f", name, "32c", "-set", name, str(value),
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
            self._last = values
        except (OSError, subprocess.SubprocessError):
            self.executable = None


class GnomeProgress:
    """Unity LauncherEntry protocol used by Dash to Dock and Ubuntu Dock."""

    def __init__(self):
        from PyQt6.QtDBus import QDBusConnection, QDBusMessage

        self._message_type = QDBusMessage
        self._bus = QDBusConnection.sessionBus()
        if not self._bus.isConnected():
            raise RuntimeError("No session bus")
        self._last = None

    def update(self, state, fraction):
        if self._bus is None:
            return
        # LauncherEntry has no indeterminate mode. Hide until a total is known.
        values = (state == 2, round(min(1.0, max(0.0, fraction)), 2) if state == 2 else 0.0)
        if values == self._last:
            return
        try:
            message = self._message_type.createSignal(
                "/com/canonical/unity/launcherentry/chksmg",
                "com.canonical.Unity.LauncherEntry", "Update",
            )
            message.setArguments([
                "application://chksmg.desktop",
                {"progress-visible": values[0], "progress": values[1]},
            ])
            if self._bus.send(message):
                self._last = values
            else:
                self._bus = None
        except RuntimeError:
            self._bus = None
