# Ceph Storage Service

A reusable Ceph-compatible storage layer for documents and chunk files.

## Overview

This service provides a simple CLI and Python helpers to manage buckets and objects in a Ceph/S3-compatible backend.

## Features
- Create and delete buckets
- List buckets and objects
- Upload files
- Download file content
- Retrieve metadata
- Delete files

---

## CLI Usage

Run from the `storage_service` directory:

```bash
poetry run python main.py list-buckets
poetry run python main.py create-bucket <bucket_name>
poetry run python main.py delete-bucket <bucket_name>
poetry run python main.py list-files <bucket_name>
poetry run python main.py upload <bucket_name> <local_file> <object_name>
poetry run python main.py delete-file <bucket_name> <object_name>
poetry run python main.py metadata <bucket_name> <object_name>
poetry run python main.py get <bucket_name> <object_name>
```

---

## Commands

- `list-buckets` — list all buckets
- `create-bucket <name>` — create a new bucket
- `delete-bucket <name>` — delete a bucket
- `list-files <bucket>` — list objects inside a bucket
- `upload <bucket> <file> <object>` — upload a local file
- `delete-file <bucket> <object>` — delete an object
- `metadata <bucket> <object>` — get object metadata
- `get <bucket> <object>` — print object content to stdout

---

## Integration

Python functions are available for direct import from `storage_service`:

```python
from bucket import create_bucket, list_buckets
from object import upload_file, list_files, get_file_metadata, get_file_stream, delete_file
```
