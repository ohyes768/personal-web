# DR001 update response validation fix

## Problem

`POST /api/macro/update/dr001` writes DR001 data successfully, but then returns
`success: false`. `UpdateResponse.data` does not accept `DR001UpdateData`, so
Pydantic rejects the otherwise valid response after persistence.

## Scope

- Add `DR001UpdateData` to the `UpdateResponse.data` union in
  `backend/macro/src/models.py`.
- Add an endpoint-level regression test that exercises a successful DR001
  update response and asserts the endpoint returns `success: true`.

## Out of scope

- No changes to DR001 fetching, CSV persistence, scheduler configuration, or
  frontend rendering.

## Verification

Run the new test first and confirm it fails because of the response-model
validation error. Then apply the one-type union change and run the focused
test plus the relevant macro backend suite.
