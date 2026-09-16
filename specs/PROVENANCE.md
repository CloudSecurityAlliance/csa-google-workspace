# Upstream Discovery document snapshots

Fetched 2026-09-16 from Google's Discovery service. These are snapshots of someone
else's moving target; re-fetch and diff before trusting them. Google revises these
documents continuously - the `revision` field is the upstream date stamp, and all
four were revised within the two weeks before this fetch.

Google publishes **Discovery documents**, not OpenAPI. Unlike Zendesk's specs, these
are linked from the official documentation and are the same artifact the Google client
libraries are generated from, so they are authoritative rather than best-effort.

| file | id | revision | source URL | sha256 | bytes |
|---|---|---|---|---|---|
| `drive-v3-discovery.json` | `drive:v3` | 20260904 | https://www.googleapis.com/discovery/v1/apis/drive/v3/rest | `c2a448c12ad05666…` | 269466 |
| `docs-v1-discovery.json` | `docs:v1` | 20260909 | https://docs.googleapis.com/$discovery/rest?version=v1 | `1fa13d42d5230242…` | 236937 |
| `sheets-v4-discovery.json` | `sheets:v4` | 20260915 | https://sheets.googleapis.com/$discovery/rest?version=v4 | `7a26036a9bdfc0b2…` | 378032 |
| `slides-v1-discovery.json` | `slides:v1` | 20260909 | https://slides.googleapis.com/$discovery/rest?version=v1 | `80e275796cc894ec…` | 227920 |

Full digests:

```
c2a448c12ad056660c8252ab2deb12ff954c50b747a3bc4abfcca3a06ea4f95e  drive-v3-discovery.json
1fa13d42d52302420d7049e1526d48a91e71b83f5bfdad5e9d9210bb059cdca2  docs-v1-discovery.json
7a26036a9bdfc0b240e9a4608e512530c7e4bcbc81e1dbc758dc23addb704d0a  sheets-v4-discovery.json
80e275796cc894ec749c6121090f047667c87ff5687587c9e746efec3dda417e  slides-v1-discovery.json
```

## Surface these describe

Method counts walk the `resources` tree; "mutating" means `httpMethod` is POST, PUT,
PATCH or DELETE.

| api | methods | mutating | top-level resources |
|---|---|---|---|
| `drive:v3` | 64 | 36 | 14 |
| `docs:v1` | 3 | 2 | 1 (`documents`) |
| `sheets:v4` | 17 | 13 | 1 (`spreadsheets`, plus 2 sub-resources) |
| `slides:v1` | 5 | 2 | 1 (`presentations`, plus 1 sub-resource) |

The method count understates the editing surface for the three document APIs, and it is
worth knowing why before sizing anything against it. Docs, Sheets and Slides each put
almost all of their write capability behind a single `batchUpdate` POST whose body is a
list of one-of request objects, so the real editing vocabulary lives in the `Request`
schema rather than in the method list: 40 request kinds for Docs, 69 for Sheets, 44 for
Slides. Drive is the opposite shape - a wide REST surface (64 methods across 14
resources) over a comparatively small type system (54 schemas).
