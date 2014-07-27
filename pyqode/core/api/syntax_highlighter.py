import logging
from pygments.styles import get_style_by_name, get_all_styles
from pygments.token import Token
import sys
import time
from pyqode.core.api.utils import TextHelper
from pyqode.core.api.mode import Mode
from pyqode.core.qt import QtGui, QtCore, QtWidgets

#: The list of color schemes keys
COLOR_SCHEME_KEYS = (
    "background",
    "highlight",
    "normal",
    "keyword",
    "builtin",
    "definition",
    "comment",
    "string",
    "docstring",
    "number",
    "instance",
    "whitespace",
    'tag',
    'self'
)
#: A sorted list of available pygments styles, for convenience
PYGMENTS_STYLES = sorted(list(get_all_styles()))

if hasattr(sys, 'frozen'):
    PYGMENTS_STYLES += ['darcula', 'qt']


class ColorScheme:
    """
    Translates a pygments style into a dictionary of colors assoociated with a
    style key.

    See :attr:`pyqode.core.api.syntax_highligter.COLOR_SCHEM_KEYS` for the
    available keys.

    """
    @property
    def name(self):
        return self._name

    @property
    def background(self):
        return self.formats['background'].background().color()

    @property
    def highlight(self):
        return self.formats['highlight'].background().color()

    def __init__(self, style):
        """
        :param style: name of the pygments style to load
        """
        self._name = style
        self._brushes = {}
        self.formats = {}
        style = get_style_by_name(style)
        self._load_formats_from_style(style)

    def _load_formats_from_style(self, style):
        # background
        self.formats['background'] = self._get_format_from_color(style.background_color)
        # highlight
        self.formats['highlight'] = self._get_format_from_color(style.highlight_color)
        # token styles
        token_key_pairs = [
            (Token.Keyword, 'keyword'),
            (Token.Text, 'normal'),
            (Token.Name.Builtin, 'builtin'),
            (Token.Name.Class, 'definition'),
            (Token.Comment, 'comment'),
            (Token.Literal.String, 'string'),
            (Token.Literal.String.Doc, 'docstring'),
            (Token.Number, 'number'),
            (Token.Name.Variable, 'instance'),
            (Token.Text.Whitespace, 'whitespace'),
            (Token.Name.Tag, 'tag'),
            (Token.Name.Builtin.Pseudo, 'self'),
            (Token.Name.Decorator, 'decorator')
        ]
        for token, key in token_key_pairs:
            self.formats[key] = self._get_format_from_style(token, style)

    def _get_format_from_color(self, color):
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(self._get_brush(color))
        return fmt

    def _get_format_from_style(self, token, style):
        """ Returns a QTextCharFormat for token by reading a Pygments style.
        """
        result = QtGui.QTextCharFormat()
        result.setForeground(self._get_brush("#000000"))
        for key, value in list(style.style_for_token(token).items()):
            if value:
                if key == 'color':
                    result.setForeground(self._get_brush(value))
                elif key == 'bgcolor':
                    result.setBackground(self._get_brush(value))
                elif key == 'bold':
                    result.setFontWeight(QtGui.QFont.Bold)
                elif key == 'italic':
                    result.setFontItalic(value)
                elif key == 'underline':
                    result.setUnderlineStyle(
                        QtGui.QTextCharFormat.SingleUnderline)
                elif key == 'sans':
                    result.setFontStyleHint(QtGui.QFont.SansSerif)
                elif key == 'roman':
                    result.setFontStyleHint(QtGui.QFont.Times)
                elif key == 'mono':
                    result.setFontStyleHint(QtGui.QFont.TypeWriter)
        return result

    def _get_brush(self, color):
        """ Returns a brush for the color.
        """
        result = self._brushes.get(color)
        if result is None:
            qcolor = self._get_color(color)
            result = QtGui.QBrush(qcolor)
            self._brushes[color] = result
        return result

    @staticmethod
    def _get_color(color):
        """ Returns a QColor built from a Pygments color string. """
        color = str(color).replace("#", "")
        qcolor = QtGui.QColor()
        qcolor.setRgb(int(color[:2], base=16),
                      int(color[2:4], base=16),
                      int(color[4:6], base=16))
        return qcolor


def _logger():
    return logging.getLogger(__name__)


class SyntaxHighlighter(QtGui.QSyntaxHighlighter, Mode):
    """
    Abstract Base class for syntax highlighter modes.

    It fills up the document with our custom block data (fold levels,
    triggers,...).

    It **does not do any syntax highlighting**, this task is left to the
    sublasses such as :class:`pyqode.core.modes.PygmentsSyntaxHighlighter`.

    Subclasses **must** override the
    :meth:`pyqode.core.api.SyntaxHighlighter.highlight_block` method to
    apply custom highlighting.

    .. note:: Since version 2.1 and for performance reasons, we store all
        our data in the block user state as bitmask. You should always
        use :class:`pyqode.core.api.TextBlockHelper` to retrieve or modify
        those data.
    """
    #: Signal emitted at the start of highlightBlock. Parameters are the
    #: highlighter instance and the current text block
    block_highlight_started = QtCore.Signal(object, object)

    #: Signal emitted at the end of highlightBlock. Parameters are the
    #: highlighter instance and the current text block
    block_highlight_finished = QtCore.Signal(object, object)

    NORMAL = 0

    @property
    def formats(self):
        return self._color_scheme.formats

    @property
    def color_scheme(self):
        return self._color_scheme

    def refresh_editor(self, color_scheme):
        self.editor.background = color_scheme.background
        self.editor.foreground = color_scheme.formats[
            'normal'].foreground().color()
        self.editor.whitespaces_foreground = color_scheme.formats[
            'whitespace'].foreground().color()
        try:
            mode = self.editor.modes.get('CaretLineHighlighterMode')
        except KeyError:
            pass
        else:
            mode.background = color_scheme.highlight
            mode.refresh()
        self.editor._reset_stylesheet()  # pylint: disable=protected-access


    @color_scheme.setter
    def color_scheme(self, color_scheme):
        self._color_scheme = color_scheme
        self.refresh_editor(color_scheme)
        self.rehighlight()

    def __init__(self, parent, color_scheme=None):
        QtGui.QSyntaxHighlighter.__init__(self,  parent)
        Mode.__init__(self)
        if not color_scheme:
            color_scheme = ColorScheme('qt')
        self._color_scheme = color_scheme
        self._spaces_ptrn = QtCore.QRegExp(r'\s+')
        # current block (with a user_data attribute)
        self.current_block = None

    def highlightBlock(self, text):  #: pylint: disable=invalid-name
        """
        Highlights a block of text.
        """
        # self.block_highlight_started.emit(self, text)
        # # # setup user data
        block = self.currentBlock()
        self.current_block = block
        if self.editor:
            self.highlight_block(text, block)

    def highlight_block(self, text, block):
        """
        Abstract method. Override this to apply syntax highlighting.

        :param text: Line of text to highlight.
        :param block: current block
        """
        raise NotImplementedError()

    def rehighlight(self):
        start = time.time()
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        super().rehighlight()
        QtWidgets.QApplication.restoreOverrideCursor()
        end = time.time()
        _logger().info('rehighlight duration: %fs' % (end - start))

    def on_install(self, editor):
        super().on_install(editor)
        self.refresh_editor(self.color_scheme)


class TextBlockUserData(QtGui.QTextBlockUserData):
    """
    Custom text block user data, mainly used to store block checker messages
    and markers.

    """
    # pylint: disable=too-many-instance-attributes, too-few-public-methods
    def __init__(self):
        super().__init__()
        #: List of checker messages associated with the block.
        self.messages = []
        #: List of markers draw by a marker panel.
        self.markers = []
