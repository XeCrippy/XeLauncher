# XeLauncher — an Xbox 360 game launcher for your wrist.
# Copyright (C) 2026 Solace 360
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <https://www.gnu.org/licenses/>.

"""XeLauncher — an Xbox 360 game launcher for your wrist.

A standalone companion to Solace 360, built for Wear OS but happy on a phone.
Every core feature speaks stock xbdm only (see :mod:`xbdm`), so it works on any
RGH/JTAG console with a debug monitor. The one exception is the optional
shutdown action, which needs an SRPC or JRPC2 plugin on the console.

    xbdm/    the console protocol, trimmed to what a launcher needs
    core/    persistence, directory listing and labelling, the live session
    ui/      theme, widgets, the app shell and one module per screen

This file is only the entry point.
"""

import flet as ft

from ui.shell import main

ft.run(main=main, assets_dir="assets")
