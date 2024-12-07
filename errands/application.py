# Copyright 2023-2024 Vlad Krupinskii <mrvladus@yandex.ru>
# SPDX-License-Identifier: MIT

import os
from subprocess import getoutput
import subprocess
from time import sleep

from gi.repository import Adw, Gio, GLib, Xdp  # type:ignore

from errands.lib.data import UserData
from errands.lib.gsettings import GSettings
from errands.lib.logging import Log
from errands.lib.notifications import ErrandsNotificationsDaemon

# from errands.lib.plugins import PluginsLoader
from errands.lib.utils import threaded
from errands.state import State
from errands.widgets.window import Window


class ErrandsApplication(Adw.Application):
    # plugins_loader: PluginsLoader = None

    def __init__(self) -> None:
        super().__init__(
            application_id=State.APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.set_resource_base_path("/io/github/mrvladus/Errands/")
        State.application = self

    @threaded
    def check_reload(self) -> None:
        """Check if there is newer version installed"""

        if State.PROFILE == "development":
            return

        TIMEOUT_SECONDS: int = 60
        portal: Xdp.Portal = Xdp.Portal()
        is_flatpak: bool = portal.running_under_flatpak()

        def __restart(*args):
            """Restart the app"""

            State.application.quit()

            if is_flatpak:
                cmd: str = "flatpak-spawn --host flatpak run io.github.mrvladus.List"
            else:
                cmd: str = "errands"

            subprocess.run(cmd)
            exit()

        def __inner_check() -> bool:
            """Get installed version"""

            try:
                version: str = ""
                if is_flatpak:
                    version: str = getoutput(
                        "flatpak-spawn --host flatpak list --app | grep io.github.mrvladus.List | awk '{ print $3 }'"
                    )
                else:
                    version: str = (
                        getoutput(
                            "cat $(whereis -b errands | cut -d ' ' -f 2) | grep VERSION"
                        )
                        .split(" ")[-1]
                        .strip('"')
                    )
                if version:
                    # If installed version is different from running then show message
                    if version != State.VERSION:
                        restart_message = Adw.MessageDialog(
                            heading=_("Errands was updated"),
                            body=_("Restart is required"),
                            transient_for=State.main_window,
                        )
                        restart_message.add_response("restart", _("Restart"))
                        restart_message.set_default_response("restart")
                        restart_message.connect("response", __restart)
                        if State.main_window.get_visible():
                            GLib.idle_add(restart_message.present)
                        else:
                            GLib.idle_add(__restart)
                        return False
                    else:
                        return True
            except Exception:
                return True

        while True:
            sleep(TIMEOUT_SECONDS)
            if not __inner_check():
                break

    def run_in_background(self):
        """Create or remove autostart desktop file"""

        Log.debug("Application: Checking autostart")

        portal: Xdp.Portal = Xdp.Portal()
        is_flatpak: bool = portal.running_under_flatpak()

        if GSettings.get("launch-on-startup"):
            if is_flatpak:
                # Request background
                portal.request_background(
                    None,
                    _("Errands need to run in the background for notifications"),
                    ["errands", "--gapplication-service"],
                    Xdp.BackgroundFlags.AUTOSTART,
                    None,
                    None,
                    None,
                )
            else:
                # Get or create autostart dir
                autostart_dir: str = os.path.join(GLib.get_home_dir(), ".config", "autostart")
                if not os.path.exists(autostart_dir):
                    os.mkdir(autostart_dir)
                autostart_file_content = f"""[Desktop Entry]
Type=Application
Name={State.APP_ID}
Exec=errands --gapplication-service"""
                # Create autostart file
                file_path: str = os.path.join(autostart_dir, f"{State.APP_ID}.desktop")
                with open(file_path, "w") as f:
                    f.write(autostart_file_content)
        else:
            if is_flatpak:
                portal.request_background(
                    None,
                    None,
                    [""],
                    Xdp.BackgroundFlags.NONE,
                    None,
                    None,
                    None,
                )
            else:
                try:
                    os.remove(
                        os.path.join(
                            GLib.get_home_dir(),
                            ".config",
                            "autostart",
                            State.APP_ID + ".desktop",
                        )
                    )
                except Exception:
                    pass

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)

        # Logging
        Log.init()
        Log.debug("Application: Startup")

        # User database
        UserData.init()

        # GSettings
        GSettings.init()

        # Background
        self.run_in_background()

        # Start notifications daemon
        ErrandsNotificationsDaemon()

        # Plugins
        # self.plugins_loader = PluginsLoader(self)

        # Initialize State
        State.init()

        # Main window
        State.main_window = Window(application=State.application)
        self.add_window(State.main_window)

        # self.check_reload()

    def do_activate(self) -> None:
        Log.debug("Application: Activate")
        if not State.main_window:
            State.main_window = Window(application=State.application)
            self.add_window(State.main_window)
        State.main_window.present()
