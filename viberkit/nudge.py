"""Make Viber read its database without the user clicking anything.

The live export only fires on a SELECT that Viber itself runs (right thread,
autocommit). Opening the chat-info "Links"/"Files"/"GIFs" pages makes Viber
query viber.db, so we invoke those buttons through Windows UI Automation:
no mouse movement, no focus change, works while Viber is minimized. These
pages only list content - we never touch any other control.

Uses PowerShell's built-in UIAutomationClient, so no extra Python dependency.
"""
import base64
import ctypes
import subprocess

# Read-only info pages, tried in turn (each first open triggers a fresh query).
SAFE_BUTTONS = ("Links", "Files", "GIFs")

_PS = r"""
param([long]$hwnd, [string]$name)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$T = [System.Windows.Automation.TreeScope]::Descendants
$root = $A::FromHandle([IntPtr]$hwnd)
function Find-Button($n) {
  $c = New-Object System.Windows.Automation.AndCondition(
    (New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)),
    (New-Object System.Windows.Automation.PropertyCondition($A::NameProperty, $n)))
  return $root.FindFirst($T, $c)
}
$el = Find-Button $name
if (-not $el) {
  # Chat info sidebar closed: open it with the chat header's Info button.
  $c = New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
  foreach ($b in $root.FindAll($T, $c)) {
    if ($b.Current.AutomationId -match '\.InfoButton_QMLTYPE_\d+$') {
      $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
      Start-Sleep -Milliseconds 800
      $el = Find-Button $name
      break
    }
  }
}
if (-not $el) { 'notfound'; exit 2 }
$el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
'invoked'
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


def poke(hwnd, attempt):
    """Invoke one safe info page; returns True if a button was invoked."""
    name = SAFE_BUTTONS[attempt % len(SAFE_BUTTONS)]
    # Wrap the script in a scriptblock so params can be passed via -EncodedCommand.
    script = f"& {{ {_PS} }} {int(hwnd)} '{name}'"
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
            capture_output=True, text=True, timeout=45, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return "invoked" in out.stdout
