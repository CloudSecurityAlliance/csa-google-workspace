from . import exceptions  # noqa: F401
from .backend import Backend
from .base import Document
from .comments import Author, Comment, CommentCollection, Location, Reply
from .documents.doc import Doc
from .documents.sheet import Sheet
from .documents.slides import Slide, Slides
from .exceptions import DetachedError
from .suggestions import Suggestion
from .workspace import Workspace

__all__ = [
    "Workspace", "Doc", "Sheet", "Slides", "exceptions",
    "Comment", "Author", "Reply", "Location",
    "Suggestion", "Slide",
    # load-bearing types for embedders / custom backends (audit #26)
    "Backend", "Document", "CommentCollection", "DetachedError",
]
__version__ = "0.1.0"
