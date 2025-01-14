import logging
logger = logging.getLogger(__name__)

import itertools
import re
import os
from functools import partial

import urwid

class FileBrowserTreeWidget(urwid.TreeWidget):
    indent_cols = 2

    def __init__(self, node):
        super().__init__(node)
        # insert an extra AttrWrap for our own use
        self._w = urwid.AttrWrap(self._w, None)
        self.marked = False
        self.update_w()

    def keypress(self, size, key):

        if self.is_leaf:
            return key
        if key == "right":
            self.get_node().tree.collapse_all()
            self.get_node().expand()
        if key == "left":
            self.get_node().collapse()
        elif self._w.selectable():
            return self.__super.keypress(size, key)
        else:
            return key

    def update_w(self):
        """Update the attributes of self.widget based on self.marked.
        """
        if self.marked:
            self._w.attr = 'marked'
            self._w.focus_attr = 'marked_focus'
        else:
            self._w.attr = "normal"
            self._w.focus_attr = 'focus'


class FlagFileWidget(FileBrowserTreeWidget):
    # apply an attribute to the expand/unexpand icons
    unexpanded_icon = urwid.AttrMap(
        urwid.TreeWidget.unexpanded_icon,
        "dirmark", "dirmark_focus"
    )
    expanded_icon = urwid.AttrMap(
        urwid.TreeWidget.expanded_icon,
        "dirmark", "dirmark_focus")

    def __init__(self, node):
        self.__super.__init__(node)
        # insert an extra AttrWrap for our own use
        self._w = urwid.AttrWrap(self._w, None)
        self.flagged = False
        self.update_w()

    def selectable(self):
        return True

    def keypress(self, size, key):
        """allow subclasses to intercept keystrokes"""
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):
        """
        Override this method to intercept keystrokes in subclasses.
        Default behavior: Toggle flagged on space, ignore other keys.
        """
        if key == " ":
            self.flagged = not self.flagged
            self.update_w()
        else:
            return key


class FileTreeWidget(FlagFileWidget):
    """Widget for individual files."""
    def __init__(self, node):
        self.__super.__init__(node)
        path = node.get_value()
        add_widget(path, self)

    def get_display_text(self):
        return self.get_node().get_key()


class EmptyWidget(FileBrowserTreeWidget):
    """A marker for expanded directories with no contents."""
    def get_display_text(self):
        return ('flag', '(empty directory)')


class ErrorWidget(FileBrowserTreeWidget):
    """A marker for errors reading directories."""

    def get_display_text(self):
        return ('error', "(error/permission denied)")


class DirectoryWidget(FlagFileWidget):
    """Widget for a directory."""
    def __init__(self, node):
        self.__super.__init__(node)
        path = node.get_value()
        add_widget(path, self)
        self.expanded = node.tree.starts_expanded(node)
        self.update_expanded_icon()

    def get_display_text(self):
        node = self.get_node()
        if node.get_depth() == 0:
            return node.tree.root
        else:
            return node.get_key()


class FileNode(urwid.TreeNode):
    """Metadata storage for individual files"""

    def __init__(self, path, parent=None):
        self.parent = parent
        depth = path.count(dir_sep()) - parent.tree.root.count(dir_sep())
        key = os.path.basename(path)
        urwid.TreeNode.__init__(self, path, key=key, parent=parent, depth=depth)

    def load_parent(self):
        parentname, myname = os.path.split(self.get_value())
        parent = DirectoryNode(parentname)
        parent.set_child_node(self.get_key(), self)
        return parent

    def load_widget(self):
        return FileTreeWidget(self)

    @property
    def full_path(self):
        path = []
        root = self
        while root.get_parent() is not None:
            path.append(root.get_key())
            root = root.get_parent()
        path.append(self.parent.tree.root)
        return dir_sep().join(reversed(path))

    def refresh(self):
        self.get_parent().refresh()


class EmptyNode(urwid.TreeNode):
    def load_widget(self):
        return EmptyWidget(self)


class ErrorNode(urwid.TreeNode):
    def load_widget(self):
        return ErrorWidget(self)


class DirectoryNode(urwid.ParentNode):
    """Metadata storage for directories"""

    def __init__(self, tree, path, parent=None):
        self.tree = tree
        if path == self.tree.root:
            depth = 0
            key = None
        else:
            depth = path.count(dir_sep()) - self.tree.root.count(dir_sep())
            key = os.path.basename(path)
        urwid.ParentNode.__init__(self, path, key=key, parent=parent,
                                  depth=depth)

    def load_parent(self):
        parentname, myname = os.path.split(self.get_value())
        parent = DirectoryNode(self.tree, parentname)
        parent.set_child_node(self.get_key(), self)
        return parent

    def load_child_keys(self):
        dirs = []
        files = []
        try:
            path = self.get_value()
            # separate dirs and files
            for a in os.listdir(path):
                if not self.tree.ignore_directories and os.path.isdir(os.path.join(path,a)):
                    dirs.append(a)
                elif not self.tree.ignore_files:
                    files.append(a)
        except OSError as e:
            depth = self.get_depth() + 1
            self._children[None] = ErrorNode(self, parent=self, key=None,
                                             depth=depth)
            return [None]

        # sort dirs and files
        dirs.sort(
            key=partial(self.tree.dir_sort_key, self.full_path),
            reverse=self.tree.dir_sort_reverse
        )
        files.sort(
            key=partial(self.tree.file_sort_key, self.full_path),
            reverse=self.tree.file_sort_reverse
        )
        # store where the first file starts
        self.dir_count = len(dirs)
        # collect dirs and files together again
        keys = dirs + files
        if self.tree.expand_empty and len(keys) == 0:
            depth=self.get_depth() + 1
            self._children[None] = EmptyNode(self, parent=self, key=None,
                                             depth=depth)
            keys = [None]
        return keys

    def load_child_node(self, key):
        """Return either a FileNode or DirectoryNode"""
        index = self.get_child_index(key)
        if key is None:
            return EmptyNode(None)
        else:
            path = os.path.join(self.get_value(), key)
            if index < self.dir_count:
                return DirectoryNode(self.tree, path, parent=self)
            else:
                path = os.path.join(self.get_value(), key)
                return FileNode(path, parent=self)

    def load_widget(self):
        return DirectoryWidget(self)

    def expand(self):
        self.get_widget().expanded = True
        self.get_widget().update_expanded_icon()

    def collapse(self):
        self.get_widget().expanded = False
        self.get_widget().update_expanded_icon()


    def find_path(self, path):
        d, p = os.path.split(path)
        node = self.get_first_child()
        while True:
            if not d:
                if node.get_key() == p:
                    return node
            elif node.get_key() == d:
                node.expand()
                return node.find_path(p) or node
            node = node.next_sibling()
            if not node:
                break


    @property
    def full_path(self):
        path = []
        root = self
        while root.get_parent() is not None:
            path.append(root.get_key())
            root = root.get_parent()
        path.append(self.tree.root)
        return dir_sep().join(reversed(path))

    def refresh(self):
        # for c in self._children:
        #     self._children.pop(c)
        self.get_child_keys(reload=True)
        parent = self.get_parent()
        if not parent:
            return
        parent.load_widget()


SPLIT_RE = re.compile(r'[a-zA-Z]+|\d+')
def sort_alpha(root, s):
    L = []
    for isdigit, group in itertools.groupby(SPLIT_RE.findall(s), key=lambda x: x.isdigit()):
        if isdigit:
            for n in group:
                L.append(('', int(n)))
        else:
            L.append((''.join(group).lower(), 0))
    return L

def sort_mtime(root, s):
    # logger.info(f"{root}, {s}")
    return os.stat(os.path.join(root, s)).st_mtime

class FileBrowser(urwid.WidgetWrap):

    signals = ["focus"]

    SORT_KEY_MAP = {
        "alpha": sort_alpha,
        "mtime": sort_mtime,
    }


    palette = [
        ('body', 'black', 'light gray'),
        ('flagged', 'black', 'dark green', ('bold','underline')),
        ('focus', 'light gray', 'dark blue', 'standout'),
        ('flagged focus', 'yellow', 'dark cyan',
                ('bold','standout','underline')),
        ('head', 'yellow', 'black', 'standout'),
        ('foot', 'light gray', 'black'),
        ('key', 'light cyan', 'black','underline'),
        ('title', 'white', 'black', 'bold'),
        ('dirmark', 'black', 'dark cyan', 'bold'),
        ('flag', 'dark gray', 'light gray'),
        ('error', 'dark red', 'light gray'),
        ]

    footer_text = [
        ('title', "Directory Browser"), "    ",
        ('key', "UP"), ",", ('key', "DOWN"), ",",
        ('key', "PAGE UP"), ",", ('key', "PAGE DOWN"),
        "  ",
        ('key', "SPACE"), "  ",
        ('key', "+"), ",",
        ('key', "-"), "  ",
        ('key', "LEFT"), "  ",
        ('key', "HOME"), "  ",
        ('key', "END"), "  ",
        ('key', "Q"),
        ]


    def __init__(self, root=None,
                 dir_sort=None,
                 file_sort=None,
                 ignore_files=False,
                 ignore_directories=False,
                 expand_empty=False):
        self.root = root or os.getcwd()
        if not isinstance(dir_sort, (tuple, list)):
            dir_sort = (dir_sort, False)
        if not isinstance(file_sort, (tuple, list)):
            file_sort = (file_sort, False)

        self.dir_sort = dir_sort
        self.file_sort = file_sort
        self.ignore_files = ignore_files
        self.ignore_directories = ignore_directories
        self.expand_empty = expand_empty
        self.last_selection = None
        cwd = os.getcwd()
        self.tree_root = DirectoryNode(self, self.root)
        self.listbox = urwid.TreeListBox(urwid.TreeWalker(self.tree_root))
        self.listbox.offset_rows = 1
        urwid.connect_signal(
            self.listbox.body, "modified", self.on_modified
        )
        super().__init__(self.listbox)


    def on_modified(self):

        # if isinstance(self.selection, DirectoryNode):
        #     if self.last_selection and self.last_selection.get_node().get_parent():
        #         self.last_selection.expanded = False
        #         self.last_selection.update_expanded_icon()
        #     self.last_selection = self.selection_widget

        self._emit("focus", self.focus_position)

    def refresh(self):
        self.selection.refresh()
        self.listbox.body._modified()

    @property
    def dir_sort_order(self):
        return self.dir_sort[0]

    @dir_sort_order.setter
    def dir_sort_order(self, value):
        self.dir_sort[0] = value

    @property
    def dir_sort_reverse(self):
        return self.dir_sort[1]

    @dir_sort_reverse.setter
    def dir_sort_reverse(self, value):
        self.dir_sort[1] = value

    @property
    def dir_sort_key(self):
        return self.SORT_KEY_MAP[self.dir_sort[0] or "alpha"]

    @property
    def file_sort_order(self):
        return self.file_sort[0]

    @file_sort_order.setter
    def file_sort_order(self, value):
        self.file_sort[0] = value

    @property
    def file_sort_reverse(self):
        return self.file_sort[1]

    @file_sort_reverse.setter
    def file_sort_reverse(self, value):
        self.file_sort[1] = value

    @property
    def file_sort_key(self):
        return self.SORT_KEY_MAP[self.file_sort[0] or "alpha"]

    def toggle_dir_sort_order(self):
        self.dir_sort_order = "mtime" if self.dir_sort_order == "alpha" else "alpha"
        self.refresh()

    def toggle_dir_sort_reverse(self):
        self.dir_sort_reverse = True if self.dir_sort_reverse == False else False
        self.refresh()

    def toggle_file_sort_order(self):
        self.file_sort_order = "mtime" if self.file_sort_order == "alpha" else "alpha"
        self.refresh()

    def toggle_file_sort_reverse(self):
        self.file_sort_reverse = True if self.file_sort_reverse == False else False
        self.refresh()

    def starts_expanded(self, node):
        return node.get_depth() < 1
        # return len(path.split(os.path.sep)) <= 1

    @property
    def body(self):
        return self.listbox.body

    @property
    def focus_position(self):
        return self.listbox.focus_position

    # @property
    # def focus_position(self):
    #     return self.listbox.focus_position

    @property
    def selection_widget(self):
        return self.body.get_focus()[0]

    @property
    def selection(self):
        return self.body.get_focus()[1]

    def collapse_all(self):

        node = self.tree_root.get_first_child()
        while True:
            if isinstance(node, DirectoryNode):
                node.collapse()
            # node.get_widget().expanded = False
            # node.get_widget().update_expanded_icon()
            node = node.next_sibling()
            if not node:
                break

    def find_path(self, path):
        return self.tree_root.find_path(path)

    # return dir_sep().join(w.get_display_text() for w in self.body.get_focus())



#######
# global cache of widgets
_widget_cache = {}

def add_widget(path, widget):
    """Add the widget for a given path"""

    _widget_cache[path] = widget

def get_flagged_names():
    """Return a list of all filenames marked as flagged."""

    l = []
    for w in _widget_cache.values():
        if w.flagged:
            l.append(w.get_node().get_value())
    return l



######
# store path components of initial current working directory
_initial_cwd = []

def store_initial_cwd(name):
    """Store the initial current working directory path components."""

    global _initial_cwd
    _initial_cwd = name.split(dir_sep())

def starts_expanded(name):
    """Return True if directory is a parent of initial cwd."""

    if name == '/':
        return True

    l = name.split(dir_sep())
    if len(l) > len(_initial_cwd):
        return False

    if l != _initial_cwd[:len(l)]:
        return False

    return True


def escape_filename_sh(name):
    """Return a hopefully safe shell-escaped version of a filename."""

    # check whether we have unprintable characters
    for ch in name:
        if ord(ch) < 32:
            # found one so use the ansi-c escaping
            return escape_filename_sh_ansic(name)

    # all printable characters, so return a double-quoted version
    name.replace('\\','\\\\')
    name.replace('"','\\"')
    name.replace('`','\\`')
    name.replace('$','\\$')
    return '"'+name+'"'


def escape_filename_sh_ansic(name):
    """Return an ansi-c shell-escaped version of a filename."""

    out =[]
    # gather the escaped characters into a list
    for ch in name:
        if ord(ch) < 32:
            out.append("\\x%02x"% ord(ch))
        elif ch == '\\':
            out.append('\\\\')
        else:
            out.append(ch)

    # slap them back together in an ansi-c quote  $'...'
    return "$'" + "".join(out) + "'"

def dir_sep():
    """Return the separator used in this os."""
    return getattr(os.path,'sep','/')


if __name__=="__main__":
    main()
