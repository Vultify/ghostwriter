"""The handful of Win32 calls Ghostwriter needs, declared with ctypes so no extra packages are required."""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_PAUSE = 0x13
VK_CAPITAL = 0x14
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_SCROLL = 0x91
VK_RCONTROL = 0xA3
VK_RMENU = 0xA5
VK_V = 0x56

ERROR_ALREADY_EXISTS = 183
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MB_ICONINFORMATION = 0x40
MB_ICONERROR = 0x10

WH_KEYBOARD_LL = 13
HC_ACTION = 0
LLKHF_INJECTED = 0x10
WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
PM_NOREMOVE = 0x0000
PM_REMOVE = 0x0001

WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
GWL_EXSTYLE = -20
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SPI_GETWORKAREA = 0x0030
ERROR_CLASS_ALREADY_EXISTS = 1410
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

BI_RGB = 0
DIB_RGB_COLORS = 0
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1
ULW_ALPHA = 0x00000002

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
MAPVK_VK_TO_VSC = 0

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
HWND_MESSAGE = wintypes.HWND(-3)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _InputUnion(ctypes.Union):
    # MOUSEINPUT is the largest member, so including it gives INPUT the size SendInput expects.
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", wintypes.BYTE),
        ("BlendFlags", wintypes.BYTE),
        ("SourceConstantAlpha", wintypes.BYTE),
        ("AlphaFormat", wintypes.BYTE),
    ]


for _func, _argtypes, _restype in (
    (user32.SetWindowsHookExW, [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD], wintypes.HHOOK),
    (user32.UnhookWindowsHookEx, [wintypes.HHOOK], wintypes.BOOL),
    (user32.CallNextHookEx, [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM], LRESULT),
    (user32.GetMessageW, [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT], wintypes.BOOL),
    (user32.PeekMessageW, [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT], wintypes.BOOL),
    (user32.PostThreadMessageW, [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
    (user32.SendInput, [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int], wintypes.UINT),
    (user32.MapVirtualKeyW, [wintypes.UINT, wintypes.UINT], wintypes.UINT),
    (user32.GetAsyncKeyState, [ctypes.c_int], ctypes.c_short),
    (user32.OpenClipboard, [wintypes.HWND], wintypes.BOOL),
    (user32.CloseClipboard, [], wintypes.BOOL),
    (user32.EmptyClipboard, [], wintypes.BOOL),
    (user32.EnumClipboardFormats, [wintypes.UINT], wintypes.UINT),
    (user32.GetClipboardData, [wintypes.UINT], wintypes.HANDLE),
    (user32.SetClipboardData, [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
    (user32.RegisterClipboardFormatW, [wintypes.LPCWSTR], wintypes.UINT),
    (user32.GetClipboardFormatNameW, [wintypes.UINT, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
    (user32.GetClipboardSequenceNumber, [], wintypes.DWORD),
    (user32.CreateWindowExW, [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                              wintypes.HINSTANCE, wintypes.LPVOID], wintypes.HWND),
    (user32.RegisterClassExW, [ctypes.POINTER(WNDCLASSEXW)], wintypes.ATOM),
    (user32.DefWindowProcW, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], LRESULT),
    (user32.DestroyWindow, [wintypes.HWND], wintypes.BOOL),
    (user32.ShowWindow, [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
    (user32.IsWindowVisible, [wintypes.HWND], wintypes.BOOL),
    (user32.GetWindowLongPtrW, [wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t),
    (user32.GetWindowRect, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
    (user32.TranslateMessage, [ctypes.POINTER(wintypes.MSG)], wintypes.BOOL),
    (user32.DispatchMessageW, [ctypes.POINTER(wintypes.MSG)], LRESULT),
    (user32.UpdateLayeredWindow, [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                  ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                  wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD], wintypes.BOOL),
    (user32.GetDC, [wintypes.HWND], wintypes.HDC),
    (user32.ReleaseDC, [wintypes.HWND, wintypes.HDC], ctypes.c_int),
    (user32.SystemParametersInfoW, [wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT], wintypes.BOOL),
    (user32.GetDpiForSystem, [], wintypes.UINT),
    (user32.SetProcessDpiAwarenessContext, [wintypes.HANDLE], wintypes.BOOL),
    (gdi32.CreateCompatibleDC, [wintypes.HDC], wintypes.HDC),
    (gdi32.CreateDIBSection, [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                              ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD], wintypes.HBITMAP),
    (gdi32.SelectObject, [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ),
    (gdi32.DeleteObject, [wintypes.HGDIOBJ], wintypes.BOOL),
    (gdi32.DeleteDC, [wintypes.HDC], wintypes.BOOL),
    (user32.MessageBoxW, [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT], ctypes.c_int),
    (user32.GetForegroundWindow, [], wintypes.HWND),
    (user32.GetKeyboardLayoutList, [ctypes.c_int, ctypes.POINTER(wintypes.HKL)], ctypes.c_int),
    (user32.VkKeyScanExW, [wintypes.WCHAR, wintypes.HKL], ctypes.c_short),
    (user32.GetWindowThreadProcessId, [wintypes.HWND, wintypes.LPDWORD], wintypes.DWORD),
    (kernel32.OpenProcess, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
    (kernel32.QueryFullProcessImageNameW, [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, wintypes.LPDWORD],
     wintypes.BOOL),
    (kernel32.CloseHandle, [wintypes.HANDLE], wintypes.BOOL),
    (kernel32.CreateMutexW, [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
    (kernel32.GetModuleHandleW, [wintypes.LPCWSTR], wintypes.HMODULE),
    (kernel32.GetCurrentThreadId, [], wintypes.DWORD),
    (kernel32.GlobalAlloc, [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL),
    (kernel32.GlobalLock, [wintypes.HGLOBAL], wintypes.LPVOID),
    (kernel32.GlobalUnlock, [wintypes.HGLOBAL], wintypes.BOOL),
    (kernel32.GlobalSize, [wintypes.HGLOBAL], ctypes.c_size_t),
    (kernel32.GlobalFree, [wintypes.HGLOBAL], wintypes.HGLOBAL),
):
    _func.argtypes = _argtypes
    _func.restype = _restype
