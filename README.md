# AddressZen Python SDK

Client for every current API operation: address search and lookup, place search, email and phone validation, and key, licensee and configuration management. Requires Python 3.12 or later; tested on 3.12, 3.13 and 3.14.

```sh
pip install addresszen
```

```python
from addresszen import AddressZen

with AddressZen("ak_test") as client:
    hits = client.find_address(query="123 Main Street", limit=5).hits
    if hits:
        address = client.retrieve_address(hits[0].id)
        print(address.zip_code)
```

`ak_test` is the public test key. Resolve the suggestion the user chooses. Empty suggestions are a normal result. The client returns Pydantic models from the API's `result` field. Read fields as attributes and use `model_dump()` for a dictionary. Reuse a client and close it with a context manager. Production keys belong in environment variables.

## Methods

| Method | Purpose |
| --- | --- |
| `find_address(query=..., ...)` | Address autocomplete |
| `retrieve_address(address, ...)` | Resolve a suggestion using the spec's USA endpoint |
| `address_verify(query=..., ...)` | Verify an address with optional ZIP or postal code, city and state inputs |
| `find_place(query=..., ...)` | Place search |
| `resolve_place(place, ...)` | Resolve a place suggestion |
| `email_validation(query=..., ...)` | Validate an email address |
| `phone_number_validation(query=..., ...)` | Validate a phone number |
| `key_availability(key)` | Public availability and licensed contexts |
| `key_details(key, user_token=...)` | Private settings and remaining lookups |
| `update_key_details(key, user_token=..., ...)` | Update selected key settings |
| `key_usage(key, user_token=..., ...)` | Usage totals and daily breakdown |
| `key_logs(key, user_token=..., ...)` | Paid lookup logs as CSV text |
| `list_licensees`, `create_licensee`, `retrieve_licensee`, `update_licensee`, `delete_licensee`, `regenerate_licensee_key` | Licensee management |
| `list_configs`, `create_config`, `retrieve_config`, `update_config`, `delete_config` | Saved configurations |

Verification uses the spec's `zip_code` parameter. For a US address, supply `query="123 Main Street", zip_code="81073"`.

Methods expose every supported input in their signatures. Required keyword arguments must be supplied. Optional `None` values are omitted, leaving defaults to the server. Dataset lists are comma-joined. String flags use `"true"` and `"false"`, as declared by the API. Parameter constraints appear in each method's docstring; scalar ranges, lengths and enums are checked before sending.

Use `help(AddressZen.find_address)` or inspect `addresszen/client.py` for parameters. Response definitions live in `addresszen/types.py`. `examples/` has a runnable script for each method.

## Keys

```python
from addresszen import AddressZen

with AddressZen("ak_test") as client:
    availability = client.key_availability("ak_test")
    print(availability.available)
```

The `key` argument identifies the key to inspect or update. Availability and `retrieve_config` need no Management Key. Other key, licensee and configuration methods require your Management Key as the keyword `user_token`; the client sends it as `Authorization: Bearer`, in place of the API key, never in the URL. Load it from your application's secret storage. Usage and logs accept `start` and `end` as UNIX timestamps in milliseconds. `key_logs` returns CSV text rather than a response model.

Update only the settings you want to change. Nested settings accept typed dictionaries from `addresszen.requests`. For example, `daily_limit={"limit": None}` disables the daily limit, `notifications={"enabled": False}` disables notifications and `allowed_urls=[]` clears the URL restriction. Omitted top-level settings remain unchanged. Nested `None` values are sent as JSON `null`.

## Errors and retries

All SDK request failures derive from `ClientError`:

- `APIError`: unsuccessful HTTP response, with `status`, `code`, `message`, `body` and raw `retry_after`
- `AuthenticationError`, `PaymentRequiredError`, `NotFoundError`, `RateLimitError` and `ServerError`: API error subclasses
- `TransportError`: connection or timeout failure before a response
- `ProtocolError`: unexpected success status, malformed envelope or a result of the wrong JSON type

A result that does not match the response schema, such as one missing a required field, is returned unvalidated with a `ResponseValidationWarning` naming the field paths. Matching fields stay typed. `warnings.simplefilter("error", ResponseValidationWarning)` makes it raise instead.

HTTP 429 and HTTP 503 with API code 5030 raise `RateLimitError`. Other 5xx responses raise `ServerError`. Exception strings include the API's `message`, for example `API request failed (HTTP 404, code 4040): Postcode not found`, and omit credentials and request URLs. `body` may contain caller input.

There are no automatic retries. A timeout may occur after a lookup was processed. Choose retry behavior in the application and bound attempts; `Retry-After` can be seconds or an HTTP date. Inputs are checked against the spec before the network call: a missing argument, wrong type or unknown settings key raises `TypeError`, and an out-of-range number, string length or pattern raises `ValueError`. Option values the SDK does not list yet pass through to the API.

## Testing and limits

Pass `transport=httpx.MockTransport(handler)` to test without network access, or override `base_url`. The default timeout is 10 seconds.

Response models validate required fields, types, lists and unions from the checked-in OpenAPI contract, and accept normal API growth: extra fields survive in `model_dump()`, option fields are plain strings so new values come through, and a `native` record from a dataset the SDK does not know yet arrives as a dictionary. An explicit `filter` returns address dictionaries containing the requested fields. The client is synchronous; run it in a worker thread when calling from an async application.

Signup is not included.

## Development

Run `uv sync --frozen`, then `make ci` and `make build`. `make generate` rebuilds the client, transport and response types from the shared generator and this brand's spec. `make check-generated` detects drift without rewriting committed files. `make format` applies Ruff fixes and formatting; `make ci` checks both. Run commands from this package directory.

## License

SEE LICENSE IN LICENSE
