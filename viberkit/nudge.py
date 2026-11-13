"""Make Viber read its database without the user clicking anything.

The live export only fires on a SELECT that Viber itself runs (right thread,
autocommit). Typing into Viber's chat search makes it query viber.db every
time (unlike chat/info pages, which Viber caches after the first open). We set
the search box text to one letter and clear it again through Windows UI
Automation: no mouse movement, no focus change, works while Viber is
minimized. Searching only reads; no other control is touched.

Uses PowerShell's built-in UIAutomationClient, so no extra Python dependency.
"""
import base64
import ctypes
import subprocess

_PS = r"""
param([long]$hwnd)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$root = $A::FromHandle([IntPtr]$hwnd)
$c = New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
foreach ($e in $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $c)) {
  if ($e.Current.AutomationId -match '\.SearchItem_QMLTYPE_\d+_QML_\d+\.TextFieldItem_QMLTYPE_\d+$') {
    $v = $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $v.SetValue('a')
    Start-Sleep -Milliseconds 1500
    $v.SetValue('')
    'invoked'; exit 0
  }
}
'notfound'
"""


def main_window(pid):
    """Return the HWND of Viber's main (QML) window, or None."""
    import ctypes.wintypes as wt  # pylint: disable=import-outside-toplevel  # Windows-only
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _cb(hwnd, _):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if owner.value == pid and user32.IsWindowVisible(hwnd) and cls.value.endswith("QWindowIcon"):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(_cb, 0)
    return found[0] if found else None


def poke(hwnd):
    """Run one search-and-clear in Viber; returns True if the search box was found."""
    # Wrap the script in a scriptblock so params can be passed via -EncodedCommand.
    script = f"& {{ {_PS} }} {int(hwnd)}"
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
            capture_output=True, text=True, timeout=45, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return "invoked" in out.stdout
