"""The handful of Win32 calls Ghostwriter needs, declared with ctypes so no extra packages are required."""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_RMENU = 0xA5
VK_V = 0x56

WH_KEYBOARD_LL = 13
HC_ACTION = 0
LLKHF_INJECTED = 0x10
WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
PM_NOREMOVE = 0x0000

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
