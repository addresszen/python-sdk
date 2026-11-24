# Changelog

## 0.2.2 (2026-11-20)

### Documentation

* Describe the Management Key config round trip in the SDK live suites

## 0.2.1 (2026-11-06)

### Bug Fixes

* Update dependencies

## 0.2.0 (2026-10-22)

### Features

* Type a verify match as a CASS verified US address or, outside the USA, an `Address`
* Return `match_information` on a verify no-match result

### Bug Fixes

* Type licensee fields and `daily.limit` as always present, matching what the API returns

## 0.1.1 (2026-10-14)

### Bug Fixes

* Update dependencies

## 0.1.0 (2026-10-12)

### Features

* Typed Python client for every AddressZen API operation, with pydantic response models
* Address lookup and key management clients
* Validate every input before sending a request
* Accept new enum values and datasets without an upgrade
* Include API error messages in exceptions and expose `ProtocolError.result`
* Identify the SDK in the `User-Agent` header
