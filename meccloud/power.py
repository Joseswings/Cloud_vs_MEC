"""Native Windows suspend notifications; install and remove on Tk's main thread."""
import ctypes
import sys


class PowerMonitor:
    def __init__(self, root, callback):
        self.hwnd = None
        if sys.platform != 'win32':
            return
        from ctypes import wintypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.user32 = user32
        self.proc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND,
                                         wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
        user32.CallWindowProcW.restype = ctypes.c_ssize_t
        self.setter = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
        self.setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        self.setter.restype = ctypes.c_void_p
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        root.update_idletasks()
        self.hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()

        def proc(hwnd, msg, wp, lp):
            if msg == 0x218 and wp in (4, 7, 18):  # suspend, resume, automatic resume
                callback()
            return user32.CallWindowProcW(self.old, hwnd, msg, wp, lp)
        self.proc = self.proc_type(proc)  # keep callback alive
        ctypes.set_last_error(0)
        self.old = self.setter(self.hwnd, -4, ctypes.cast(self.proc, ctypes.c_void_p))
        if not self.old:
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.hwnd:
            self.setter(self.hwnd, -4, self.old)
            self.hwnd = None
