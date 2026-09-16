"""Resolve a Viber sticker id to its cached PNG on disk.

Viber stores stickers as zero-padded, 8-digit ids under
%APPDATA%\\ViberPC\\data\\stickers\\<group>\\<bucket>\\<00000000>.png
"""
import glob
import os

from . import config


def resolve(sticker_id):
    """Return the PNG path for a sticker id, or '' if not found."""
    root = config.stickers_dir()
    if not sticker_id or not os.path.isdir(root):
        return ""
    try:
        sid = int(sticker_id)
    except (TypeError, ValueError):
        return ""
    hits = glob.glob(os.path.join(root, "**", f"{sid:08d}.png"), recursive=True)
    return hits[0] if hits else ""
