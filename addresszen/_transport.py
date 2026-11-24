"""Connection lifecycle and envelope handling shared by generated methods."""

from __future__ import annotations

import platform
import re
import warnings
from collections.abc import Mapping
from functools import cache
from importlib.metadata import version
from types import UnionType
from typing import Annotated, Any, Literal, Self, TypeAliasType, Union, cast, get_args, get_origin
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Discriminator, Tag, TypeAdapter, ValidationError

from .errors import ProtocolError, ResponseValidationWarning, TransportError, error_for

BASE_URL = "https://api.addresszen.com/v1"
USER_AGENT = f"addresszen-python-sdk/{version('addresszen')} python/{platform.python_version()}"


def segment(value: str | int) -> str:
    """Encode a single non-empty path segment without treating it as a URL."""
    text = str(value)
    if not text or text in {".", ".."}:
        raise ValueError("Path identifiers must be non-empty and cannot be dot segments")
    return quote(text, safe="")


def fields(values: Mapping[str, object]) -> dict[str, object]:
    """Omit optional inputs; preserve false, zero and empty strings."""
    return {key: value for key, value in values.items() if value is not None}


TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (Mapping,),
}


def check(name: str, value: object, schema: Mapping[str, Any]) -> None:
    """Raise TypeError or ValueError when an input breaks its spec schema. Messages omit the value."""
    if value is None:
        if not schema.get("nullable"):
            raise TypeError(f"{name} cannot be None")
        return
    kind = schema.get("type")
    if kind and (not isinstance(value, TYPES[kind]) or (isinstance(value, bool) and kind != "boolean")):
        raise TypeError(f"{name} must be a{'n' if kind[0] in 'aeiou' else ''} {kind}")
    broken: str | None = None
    if isinstance(value, int | float) and not isinstance(value, bool):
        if value < schema.get("minimum", value):
            broken = "minimum"
        elif value > schema.get("maximum", value):
            broken = "maximum"
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            broken = "minLength"
        elif len(value) > schema.get("maxLength", len(value)):
            broken = "maxLength"
        elif "pattern" in schema and not re.search(schema["pattern"], value):
            broken = "pattern"
    elif isinstance(value, list | tuple):
        size = len(cast("list[object]", value))
        if size < schema.get("minItems", 0):
            broken = "minItems"
        elif size > schema.get("maxItems", size):
            broken = "maxItems"
    if broken:
        raise ValueError(f"{name} must satisfy {broken}={schema[broken]!r}")
    if "items" in schema:
        for index, item in enumerate(cast("list[object]", value)):
            check(f"{name}[{index}]", item, schema["items"])
    if "properties" in schema:
        entries = cast("Mapping[str, object]", value)
        properties: Mapping[str, Any] = schema["properties"]
        unknown = sorted(set(entries) - set(properties))
        if unknown:
            raise TypeError(f"{name} has unknown keys: {', '.join(map(str, unknown))}")
        missing = [key for key in schema.get("required", []) if key not in entries]
        if missing:
            raise TypeError(f"{name} is missing keys: {', '.join(missing)}")
        for key, item in entries.items():
            check(f"{name}.{key}", item, properties[key])


def check_inputs(schemas: Mapping[str, Mapping[str, Any]], **values: object) -> None:
    """Check every supplied argument; None means omitted."""
    for name, value in values.items():
        if value is not None:
            check(name, value, schemas[name])


@cache
def adapter(schema: Any) -> TypeAdapter[Any]:
    return TypeAdapter(schema)


def mismatches(schema: Any, value: object) -> int:
    """How many validation errors value has against schema."""
    try:
        adapter(schema).validate_python(value)
    except ValidationError as error:
        return error.error_count()
    return 0


def lenient(schema: Any, value: object) -> Any:
    """Keep what validates and construct models around what does not; anything else stays raw."""
    if not mismatches(schema, value):
        return adapter(schema).validate_python(value)
    while isinstance(schema, TypeAliasType):
        schema = schema.__value__
    origin = get_origin(schema)
    if origin is Annotated:
        inner, *metadata = get_args(schema)
        for item in metadata:
            if isinstance(item, Discriminator) and callable(item.discriminator):
                tag = item.discriminator(value)
                for member in get_args(inner):
                    if any(isinstance(m, Tag) and m.tag == tag for m in getattr(member, "__metadata__", ())):
                        return lenient(member, value)
        return lenient(inner, value)
    if origin is Union or origin is UnionType:
        # Closest member by error count; None only fits a null.
        members = [member for member in get_args(schema) if member is not type(None)] if value is not None else []
        return lenient(min(members, key=lambda member: mismatches(member, value)), value) if members else value
    if origin is list and isinstance(value, list):
        return [lenient(get_args(schema)[0], item) for item in cast("list[object]", value)]
    if isinstance(schema, type) and issubclass(schema, BaseModel) and isinstance(value, dict):
        data = dict(cast("dict[str, Any]", value))
        for name, field in schema.model_fields.items():
            key = field.alias or name
            if key in data:
                data[key] = lenient(field.rebuild_annotation(), data[key])
        return schema.model_construct(**data)
    return value


def validate(schema: Any, value: object, operation: str) -> Any:
    """Validate a result. A mismatch with the spec warns and returns the result unvalidated.

    The warning names field paths, never payload values.
    """
    try:
        return adapter(schema).validate_python(value)
    except ValidationError as error:
        details = error.errors(include_input=False)
        locations = ", ".join(".".join(map(str, item["loc"])) for item in details[:8])
        if len(details) > 8:
            locations += f" (+{len(details) - 8} more)"
        warnings.warn(
            f"{operation} result does not match the API spec at: {locations}. Returned unvalidated.",
            ResponseValidationWarning,
            stacklevel=3,
        )
        return lenient(schema, value)


class Transport:
    """Synchronous connection pool. Use a context manager or call close().

    api_key: API key, sent as `Authorization: Bearer` to the operations that take it. Methods that take a
        Management Key (`user_token`) send that instead.
    timeout: Per-request HTTPX timeout in seconds, default 10.
    base_url: API root including /v1, or a test server URL.
    transport: Optional HTTPX transport for offline tests.

    Requests are never retried automatically, including billable lookups.
    """

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 10.0,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": USER_AGENT},
        )
        self._api_key = api_key

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection pool."""
        self._http.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
        result_shape: Literal["object", "array", "csv"] = "object",
        token: str | None = None,
    ) -> object:
        params: dict[str, Any] = {}
        for key, value in fields(query or {}).items():
            params[key] = (
                ",".join(str(item) for item in cast("list[object]", value)) if isinstance(value, list) else value
            )
        # The operation's one credential, API key or Management Key, or none for public operations.
        headers = {"Authorization": f"Bearer {token}"} if token else None
        try:
            response = self._http.request(method, path.lstrip("/"), params=params, json=body, headers=headers)
        except httpx.RequestError:
            raise TransportError("Request failed before a response was received; no retry was made") from None
        try:
            payload: object = response.json()
        except ValueError:
            payload = None
        envelope = cast("dict[str, Any]", payload) if isinstance(payload, dict) else {}
        if not 200 <= response.status_code < 300:
            raise error_for(response.status_code, envelope, response.headers.get("Retry-After"))
        if response.status_code != 200:
            raise ProtocolError(f"Unexpected success status {response.status_code}")
        if result_shape == "csv":
            # The API sends `text/csv name="..."`, a space before the parameter rather than a
            # semicolon, so the media type ends at the first semicolon or whitespace.
            media_type = (response.headers.get("Content-Type", "").replace(";", " ").split() or [""])[0].lower()
            if media_type != "text/csv":
                raise ProtocolError("Expected a CSV response")
            return response.text
        if envelope.get("code") != 2000 or "result" not in envelope or envelope["result"] is None:
            raise ProtocolError("Expected a JSON success envelope with code 2000 and a result")
        result = envelope["result"]
        expected = list if result_shape == "array" else dict
        if not isinstance(result, expected):
            raise ProtocolError(f"Expected result to be a JSON {result_shape}")
        return cast("list[object] | dict[str, object]", result)
