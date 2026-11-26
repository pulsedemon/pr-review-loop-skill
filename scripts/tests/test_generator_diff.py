"""unified diff records follow the output stream's line endings."""

import io
from contextlib import redirect_stderr
from pathlib import Path

from generator_io import emit_drift_diff


def test_diff_on_crlf_stream_preserves_unicode_content_and_marks_unterminated_lines() -> None:
    raw = io.BytesIO()
    with io.TextIOWrapper(raw, encoding="utf-8", newline="\r\n", write_through=True) as stream:
        with redirect_stderr(stream):
            emit_drift_diff(Path("target.md"), "left\u2028right\r\nold", "left\u2028right\r\nnew")
        output = raw.getvalue()

    assert output == "\r\n".join(
        [
            "--- target.md",
            "+++ target.md (regenerated)",
            "@@ -1,2 +1,2 @@",
            " left\u2028right",
            "-old",
            r"\ No newline at end of file",
            "+new",
            r"\ No newline at end of file",
            "",
        ]
    ).encode("utf-8")
