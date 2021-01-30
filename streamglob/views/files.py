import logging
logger = logging.getLogger(__name__)
import asyncio
import re

import urwid
from panwid.keymap import *

from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from .. import model
from ..utils import strip_emoji
from .. import config
from ..widgets import *
from .. import providers
# from ..widgets.browser import FileBrowser, DirectoryNode, FileNode
from ..providers.base import SynchronizedPlayerMixin

@model.attrclass()
class FilesPlayMediaTask(model.PlayMediaTask):
    pass

class FilesViewEventHandler(FileSystemEventHandler):

    def __init__(self, view):
        self.view = view
        self.refresh_task = None
        super().__init__()

    def on_any_event(self, event):
        self.view.updated = True

MEDIA_URI_RE=re.compile("uri=(.*)=\.")

@keymapped()
class FilesView(SynchronizedPlayerMixin, StreamglobView):

    signals = ["requery"]

    KEYMAP = {
        "meta p": "preview_all",
        "ctrl r": "refresh"
    }

    def __init__(self):

        self.browser = FileBrowser(
            self.root,
            dir_sort = config.settings.profile.get_path("files.dir_sort"),
            file_sort = config.settings.profile.get_path("files.file_sort"),
            ignore_files=False
        )
        self.pile  = urwid.Pile([
            ('weight', 1, self.browser),
        ])
        super().__init__(self.pile)
        urwid.connect_signal(self.browser, "focus", self.on_focus)
        self.updated = False
        state.event_loop.create_task(self.check_updated())
        # self._emit("requery", self)

    def keypress(self, size, key):

        if key == "s":
            self.browser.toggle_file_sort_order()
        elif key == "S":
            self.browser.toggle_file_sort_reverse()
        elif key == "d":
            self.browser.toggle_dir_sort_order()
        elif key == "D":
            self.browser.toggle_dir_sort_reverse()
        elif key == ".":
            filename = os.path.basename(self.browser.selection.full_path)
            try:
                uri = MEDIA_URI_RE.search(filename).groups()[0].replace("+", "/")
                providers.parse_uri(uri)
            except (AttributeError, IndexError):
                pass
        else:
            return super().keypress(size, key)

    async def check_updated(self):
        while True:
            if self.updated:
                self.refresh()
                self.updated = False
            await asyncio.sleep(1)

    @property
    def root(self):
        return os.path.expanduser(
            config.settings.profile.get_path("output.path")
            or "."
        )

    def on_focus(self, source, selection):

        if isinstance(selection, DirectoryNode):
            self.monitor_path(selection.full_path)
        elif isinstance(selection, FileNode):
            state.event_loop.create_task(self.preview_all())

    def monitor_path(self, path):
        # FIXME: broken -- spurious updates when files haven't changed
        return
        if path == self.root:
            return
        logger.info(f"monitor_path: {path}")
        if getattr(self, "observer", None):
            self.observer.stop()
        self.observer = PollingObserver(5)
        self.observer.schedule(
            FilesViewEventHandler(self), path, recursive=True
        )
        self.observer.start()

    def create_task(self, listing, sources):
        return FilesPlayMediaTask.attr_class(
            title=listing.title,
            sources=sources
        )


    @property
    def play_items(self):
        return [
            AttrDict(
                title = "foo",
                url = self.browser.selection.full_path
            )
        ]

    def refresh(self):
        self.browser.refresh()

    # def on_view_activate(self):
    #     state.event_loop.create_task(self.play_empty())

    def __len__(self):
        return 1
    def __iter__(self):
        return iter(self.browser.selection.full_path)