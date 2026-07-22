import logging

from .. import _cellmap
from ..base import Document

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

log = logging.getLogger(__name__)


class Sheet(Document):
    """Google Sheets. Comment->A1 cell mapping is best-effort (XLSX export + match)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cell_map_cache = None

    @property
    def tabs(self) -> list[str]:
        ss = self._backend.get_spreadsheet(self.id)
        return [s["properties"]["title"] for s in ss.get("sheets", [])]

    def values(self, a1_range: str) -> list:
        return self._backend.get_values(self.id, a1_range)

    def _quote_tab(self, title: str) -> str:
        import re
        if title.replace("_", "").isalnum() and not re.fullmatch(r"[A-Za-z]{1,3}\d+", title):
            return title
        return "'" + title.replace("'", "''") + "'"

    def _gid(self, title=None):
        sheets = self._backend.get_spreadsheet(self.id).get("sheets", [])
        for s in sheets:
            props = s.get("properties", {})
            if title is None or props.get("title") == title:
                return props.get("sheetId", 0)
        return 0

    def as_text(self) -> str:
        rng = self._quote_tab(self.tabs[0]) if self.tabs else "A1:Z1000"
        rows = self._backend.get_values(self.id, rng)
        return "\n".join("\t".join(str(c) for c in row) for row in rows)

    def create_comment(self, text: str, cell: str | None = None):
        self._require_writable()
        self._cell_map_cache = None
        if cell is None:
            return super().create_comment(text)
        gid = self._gid()
        link = f"{self.url.split('/edit')[0]}/edit#gid={gid}&range={cell}"
        return super().create_comment(f"{text}\n\n{link}")

    def _cell_map(self) -> dict:
        if self._cell_map_cache is not None:
            return self._cell_map_cache
        import xml.etree.ElementTree as _ET
        import zipfile

        from defusedxml.common import DefusedXmlException
        from googleapiclient.errors import HttpError

        from ..comments import Comment
        from ..exceptions import CsaWorkspaceError
        try:
            xlsx = self._backend.export_file(self.id, _XLSX)
            roots = _cellmap.parse_xlsx_comments(xlsx)
            raw = self._backend.list_comments(self.id, include_deleted=False)
        except (CsaWorkspaceError, HttpError, zipfile.BadZipFile,
                _ET.ParseError, DefusedXmlException) as e:
            # transient/malformed/malicious/export-cap: degrade to location=None WITHOUT
            # memoizing (so a later call retries), and record why so callers can tell this
            # apart from a genuine no-match (spec §8: location=None + a recorded warning).
            log.warning("cell mapping unavailable for sheet %s (%s: %s); "
                        "comments will have location=None", self.id, type(e).__name__, e)
            return {}
        comments = [Comment.from_api(d) for d in raw]
        self._cell_map_cache = _cellmap.match_locations(comments, roots)   # pure; a bug here propagates
        return self._cell_map_cache

    def _locate_comment(self, raw: dict):
        return self._cell_map().get(raw.get("id"))

    def comments_by_cell(self, cell: str) -> list:
        return [c for c in self.comments.all() if c.location and c.location.cell == cell]

    def reload(self) -> None:
        self._cell_map_cache = None

    def update(self, a1_range: str, values: list, value_input_option: str = "RAW") -> None:
        self._require_writable()
        self._cell_map_cache = None
        self._backend.sheets_values_update(self.id, a1_range, values, value_input_option)

    def clear(self, a1_range: str) -> None:
        self._require_writable()
        self._cell_map_cache = None
        self._backend.sheets_values_clear(self.id, a1_range)

    def batch_update(self, requests: list) -> dict:
        self._require_writable()
        self._cell_map_cache = None
        return self._backend.sheets_batch_update(self.id, requests)
