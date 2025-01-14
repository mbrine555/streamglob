import logging
logger = logging.getLogger(__name__)
import os

import urwid
from panwid.keymap import *

from ..state import *
from .. import config
from .. import providers
from ..widgets import *
from ..providers.base import SynchronizedPlayerMixin

class ProviderToolbar(urwid.WidgetWrap):

    signals = ["provider_change", "profile_change", "view_change"] # "preview_change"
    def __init__(self, default_provider):

        def format_provider(n, p):
            return p.NAME if p.config_is_valid else f"* {p.NAME}"

        def providers_sort_key(p):
            k, v = p
            # providers = list(config.settings.profile.providers.keys())
            # if k in providers:
            # raise Exception(v)
            if v.config_is_valid:
                return (0, str(v.NAME))
            else:
                return (1, str(v.NAME))

        self.provider_dropdown = BaseDropdown(AttrDict(
            [(format_provider(n, p), n)
              for n, p in sorted(
                      providers.PROVIDERS.items(),
                      key = providers_sort_key
              )]
        ) , label="Provider", default=default_provider, margin=1)

        urwid.connect_signal(
            self.provider_dropdown, "change",
            lambda w, b, v: self._emit("provider_change", v)
        )

        self.preview_dropdown_placeholder = urwid.WidgetPlaceholder(urwid.Text(""))

        self.view_dropdown_placeholder = urwid.WidgetPlaceholder(urwid.Text(""))

        self.max_concurrent_tasks_widget = providers.filters.IntegerTextFilterWidget(
            default=config.settings.tasks.max,
                minimum=1
        )

        def set_max_concurrent_tasks(v):
            if v:
                config.settings.tasks.max = int(v)

        self.max_concurrent_tasks_widget.connect("changed", set_max_concurrent_tasks)

        self.profile_dropdown = BaseDropdown(
            AttrDict(
                [ (k, k) for k in config.settings.profiles.keys()]
            ),
            label="Profile",
            default=config.settings.profile_name, margin=1
        )

        urwid.connect_signal(
            self.profile_dropdown, "change",
            lambda w, b, v: self._emit("profile_change", v)
        )

        self.columns = urwid.Columns([
            # ('weight', 1, urwid.Padding(urwid.Edit("foo"))),
            (self.provider_dropdown.width, self.provider_dropdown),
            ("weight", 1, urwid.Padding(urwid.Text(""))),
            (20, self.view_dropdown_placeholder),
            # (20, self.preview_dropdown_placeholder),
            # (1, urwid.Divider(u"\N{BOX DRAWINGS LIGHT VERTICAL}")),
            ("pack", urwid.Text(("Downloads"))),
            (5, self.max_concurrent_tasks_widget),
            ("weight", 1, urwid.Padding(urwid.Text(""))),
            (self.profile_dropdown.width, self.profile_dropdown),
        ], dividechars=3)
        # self.filler = urwid.Filler(self.columns)
        super(ProviderToolbar, self).__init__(urwid.Filler(self.columns))

    def cycle_provider(self, step=1):

        self.provider_dropdown.cycle(step)

    def cycle_preview_type(self, step=1):

        self.preview_dropdown.cycle(step)

    # @property
    # def provider(self):
    #     return (self.provider_dropdown.selected_label)

    def update_provider_config(self, preview_types, provider_config):

        self.view_dropdown = BaseDropdown(
            AttrDict(
                [ (k, k) for k in provider_config.views.keys()]
            ),
            label="View", margin=1
        )

        urwid.connect_signal(
            self.view_dropdown, "change",
            lambda w, b, v: self._emit("view_change", v)
        )

        self.view_dropdown_placeholder.original_widget = self.view_dropdown

        self.preview_dropdown = BaseDropdown(
            AttrDict([
                (pt.title(), pt)
                for pt in preview_types
            ]),
            label="Preview",
            default=provider_config.auto_preview.default or "default",
            margin=1
        )

        urwid.connect_signal(
            self.preview_dropdown, "change",
            lambda w, b, v: self._emit("preview_change", v)
        )

        self.preview_dropdown_placeholder.original_widget = self.preview_dropdown

MEDIA_URI_RE=re.compile("uri=(.*)=\.")

@keymapped()
class ListingsView(StreamglobView):


    KEYMAP = {
        "meta [": ("cycle_provider", [-1]),
        "meta ]": ("cycle_provider", [1]),
        "meta {": ("cycle_preview_type", [-1]),
        "meta }": ("cycle_preview_type", [1]),
    }

    SETTINGS = ["provider", "profile", "preview"]

    VIEW_KEYS = "!@#$%^&*()"

    # def __init__(self, provider_name):
    def __init__(self):
        self.provider = None
        self.provider_view_placeholder = urwid.WidgetPlaceholder(
            urwid.Filler(urwid.Text(""))
        )
        self.toolbar_placeholder = urwid.WidgetPlaceholder(
            urwid.Filler(urwid.Text(""))
        )

        self.pile  = urwid.Pile([
            (1, self.toolbar_placeholder),
            (1, urwid.Filler(urwid.Divider("-"))),
            ('weight', 1, self.provider_view_placeholder),
        ])
        self.pile.selectable = lambda: True
        super().__init__(self.pile)

    def set_provider(self, provider_name):
        self.provider = providers.get(provider_name)
        if  getattr(self, "toolbar", None):
            self.toolbar.provider_dropdown.value = self.provider.IDENTIFIER
        else:
            self.toolbar = ProviderToolbar(self.provider.IDENTIFIER)
            self.toolbar_placeholder.original_widget = self.toolbar
            urwid.connect_signal(
                self.toolbar, "provider_change",
                lambda w, p: self.set_provider(p)
            )

            urwid.connect_signal(
                self.toolbar, "view_change",
                lambda w, v: self.set_view(v)
            )

            # self.set_view(self.provider.provider_data.get("selected_view"))

            def profile_change(p):
                config.settings.toggle_profile(p)
                player.Player.load()

            urwid.connect_signal(
                self.toolbar, "profile_change",
                lambda w, p: profile_change(p)
            )

            # urwid.connect_signal(
            #     self.toolbar, "preview_change",
            #     lambda w, p: self.provider.reset()
            # )

        if self.provider:
            self.provider.deactivate()
        logger.info(f"on_set_provider: {self.provider.IDENTIFIER} {self.provider.view}")
        self.provider_view_placeholder.original_widget = self.provider.view
        self.toolbar.update_provider_config(
            self.provider.PREVIEW_TYPES,
            self.provider.config
        )
        if self.provider.config_is_valid:
            self.pile.focus_position = 2
        else:
            self.pile.focus_position = 0
        for name, value in self.provider.default_filter_values.items():
            if name not in self.SETTINGS:
                continue
            setattr(self, name, value)
        if self.provider.provider_data.get("selected_view"):
            self.toolbar.view_dropdown.selected_label = self.provider.provider_data.get("selected_view")

        state.app_data.selected_provider = self.provider.IDENTIFIER
        state.app_data.save()
        self.provider.activate()
        state.files_view.load_browser(self.provider.output_path)

    def set_view(self, name):
        view = self.provider.config.views[name]
        self.provider.toolbar.apply_filter_state(view.filters)
        if view.sort:
            self.provider.sort(*view.sort)
        self.provider.provider_data["selected_view"] = name
        self.provider.save_provider_data()

    @property
    def profile(self):
        return self.toolbar.profile_dropdown.value

    @profile.setter
    def profile(self, value):
        self.toolbar.profile_dropdown.value = value

    @property
    def preview(self):
        return self.toolbar.preview_dropdown.value

    @preview.setter
    def preview(self, value):
        self.toolbar.preview_dropdown.value = value

    def cycle_provider(self, step=1):
        self.toolbar.cycle_provider(step)

    def cycle_preview_type(self, step=1):
        self.toolbar.cycle_preview_type(step)

    def activate(self):
        self.set_provider(self.provider.IDENTIFIER)

    @property
    def preview_mode(self):
        return self.toolbar.preview_dropdown.value

    def on_view_activate(self):

        async def activate_preview_player():
            if self.provider.auto_preview_enabled:
                await self.provider.view.preview_all()

        # FIXME: this is smelly
        if hasattr(self.provider.view, "preview_all"):
            state.event_loop.create_task(activate_preview_player())

    def keypress(self, size, key):
        if key in self.VIEW_KEYS:
            idx = self.VIEW_KEYS.index(key)
            if idx >= len(self.provider.config.views):
                return
            self.toolbar.view_dropdown.focus_position = idx
            return
        return super().keypress(size, key)

    def find_source(self, listing):

        filename = os.path.basename(listing.full_path)
        try:
            uri = MEDIA_URI_RE.search(filename).groups()[0].replace("+", "/")
            (_, provider, _, _) = providers.parse_uri(uri)
            if provider.IDENTIFIER != self.provider:
                self.set_provider(provider.IDENTIFIER)
        except (AttributeError, IndexError):
            pass
        state.main_view.focus_widget(self)
