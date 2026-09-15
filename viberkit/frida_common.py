"""Shared frida helpers (frida 17 API)."""
import frida


def get_device():
    return frida.get_local_device()


def get_viber_pid():
    """PID of the running Viber, or None."""
    procs = [p for p in get_device().enumerate_processes() if "viber" in p.name.lower()]
    return procs[0].pid if procs else None


def require_viber():
    pid = get_viber_pid()
    if not pid:
        raise SystemExit("[X] Viber is not running / logged in. Start Viber Desktop and sign in.")
    return pid
