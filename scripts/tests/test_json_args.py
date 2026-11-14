"""Tests for scripts/_json_args.py."""

from __future__ import annotations

import json

import pytest
from _json_args import load_json_or_file  # type: ignore[import-not-found]


class _Boom(ValueError):
    """Sentinel exception class so the tests can assert error_cls routing."""


def test_returns_parsed_inline_json() -> None:
    result = load_json_or_file(
        inline='{"a":1,"b":[2,3]}',
        file_path=None,
        label="thing",
        flag_stem="thing",
        error_cls=_Boom,
    )

    assert result == {"a": 1, "b": [2, 3]}


def test_returns_parsed_file_json(tmp_path) -> None:
    payload = {"a": 1, "b": [2, 3]}
    target = tmp_path / "payload.json"
    target.write_text(json.dumps(payload), encoding="utf-8")

    result = load_json_or_file(
        inline=None,
        file_path=str(target),
        label="thing",
        flag_stem="thing",
        error_cls=_Boom,
    )

    assert result == payload


def test_rejects_both_inline_and_file_provided(tmp_path) -> None:
    target = tmp_path / "payload.json"
    target.write_text("{}", encoding="utf-8")

    with pytest.raises(_Boom, match="--thing-json and --thing-json-file are mutually exclusive"):
        load_json_or_file(
            inline="{}",
            file_path=str(target),
            label="thing",
            flag_stem="thing",
            error_cls=_Boom,
        )


def test_rejects_missing_input_when_required() -> None:
    with pytest.raises(_Boom, match="one of --thing-json or --thing-json-file is required"):
        load_json_or_file(
            inline=None,
            file_path=None,
            label="thing",
            flag_stem="thing",
            error_cls=_Boom,
        )


def test_returns_none_when_optional_and_missing() -> None:
    result = load_json_or_file(
        inline=None,
        file_path=None,
        label="thing",
        flag_stem="thing",
        error_cls=_Boom,
        required=False,
    )

    assert result is None


def test_raises_via_error_cls_for_malformed_inline_json() -> None:
    with pytest.raises(_Boom, match="failed to parse thing JSON"):
        load_json_or_file(
            inline="{broken",
            file_path=None,
            label="thing",
            flag_stem="thing",
            error_cls=_Boom,
        )


def test_raises_via_error_cls_for_malformed_file_json(tmp_path) -> None:
    target = tmp_path / "payload.json"
    target.write_text("{broken", encoding="utf-8")

    with pytest.raises(_Boom, match="failed to parse thing JSON"):
        load_json_or_file(
            inline=None,
            file_path=str(target),
            label="thing",
            flag_stem="thing",
            error_cls=_Boom,
        )


def test_raises_via_error_cls_for_missing_file(tmp_path) -> None:
    with pytest.raises(_Boom, match="failed to read thing JSON file"):
        load_json_or_file(
            inline=None,
            file_path=str(tmp_path / "does-not-exist.json"),
            label="thing",
            flag_stem="thing",
            error_cls=_Boom,
        )
