"""
Integration test: recreate storage buckets that already hold data, and time it.

Needs a running tools-api and RustFS, with the same RUSTFS_* env vars the API
uses (the admin credentials are used to upload the test objects). Run with:

    pytest -s tests/integration
"""
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import certifi
import httpx
import pytest
import urllib3
from minio import Minio
from minio.error import InvalidResponseError, S3Error, ServerError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))
from util import storage  # noqa: E402

pytestmark = pytest.mark.skipif(
    not all(os.getenv(v) for v in ("RUSTFS_ENDPOINT", "RUSTFS_ACCESS_KEY_ID", "RUSTFS_SECRET_KEY")),
    reason="RUSTFS_ENDPOINT / RUSTFS_ACCESS_KEY_ID / RUSTFS_SECRET_KEY not set",
)

TOOLS_API_URL = os.getenv("TOOLS_API_URL", "http://localhost:8080")
CAPTAIN_DOMAIN = os.getenv("STORAGE_TEST_CAPTAIN_DOMAIN", "storage-timing-test.example.com")
OBJECT_COUNT = int(os.getenv("STORAGE_TEST_OBJECT_COUNT", "5000"))
OBJECT_SIZE = int(float(os.getenv("STORAGE_TEST_OBJECT_SIZE_MB", "1")) * 1024 * 1024)
UPLOAD_WORKERS = int(os.getenv("STORAGE_TEST_UPLOAD_WORKERS", "8"))
UPLOAD_MAX_RETRIES = int(os.getenv("STORAGE_TEST_UPLOAD_MAX_RETRIES", "8"))
RETRYABLE_STATUSES = {500, 502, 503, 504}


def _create_buckets():
    """Call the API and return (bucket_prefix, elapsed_seconds)."""
    started = time.monotonic()
    response = httpx.post(
        f"{TOOLS_API_URL}/v1/storage-buckets",
        json={"captain_domain": CAPTAIN_DOMAIN},
        timeout=900,
    )
    elapsed = time.monotonic() - started
    assert response.status_code == 200, response.text
    match = re.search(r"bucket: (\S+)-thanos", response.text)
    assert match, f"no bucket prefix in response:\n{response.text}"
    return match.group(1), elapsed


def _upload_client():
    """
    A client for the uploads whose HTTP layer does not retry 5xx responses.

    minio-py's default client retries 5xx 5 times within ~3s and then raises a
    bare urllib3 MaxRetryError, dropping RustFS's error body. Here 5xx surfaces
    as an S3Error (with its code, e.g. SlowDown) and ``_upload_objects`` retries
    it with a longer backoff, counting how often RustFS pushed back.
    """
    http_client = urllib3.PoolManager(
        maxsize=UPLOAD_WORKERS,
        timeout=urllib3.Timeout(connect=300, read=300),
        cert_reqs="CERT_REQUIRED",
        ca_certs=os.environ.get("SSL_CERT_FILE") or certifi.where(),
        retries=urllib3.Retry(total=3, backoff_factor=0.2, status_forcelist=[]),
    )
    return Minio(
        storage.RUSTFS_ENDPOINT,
        access_key=storage.ACCESS_KEY,
        secret_key=storage.SECRET_KEY,
        secure=storage.USE_SSL,
        region=storage.RUSTFS_REGION,
        http_client=http_client,
    )


def _error_status(error):
    if isinstance(error, S3Error):
        return error.response.status
    if isinstance(error, ServerError):
        return error.status_code
    return error._code  # InvalidResponseError


def _upload_objects(bucket_name):
    """Upload the test objects and return {error description: retry count}."""
    client = _upload_client()
    retries = {}
    lock = threading.Lock()

    def upload(i):
        name = f"obj-{i:05d}"
        data = os.urandom(OBJECT_SIZE)
        for attempt in range(UPLOAD_MAX_RETRIES + 1):
            try:
                client.put_object(bucket_name, name, BytesIO(data), OBJECT_SIZE)
                return
            except (S3Error, ServerError, InvalidResponseError) as e:
                status = _error_status(e)
                if status not in RETRYABLE_STATUSES or attempt == UPLOAD_MAX_RETRIES:
                    raise AssertionError(
                        f"upload of {name} failed after {attempt} retries (HTTP {status}): {e}"
                    ) from e
                key = f"HTTP {status} {getattr(e, 'code', '')}".strip()
                with lock:
                    retries[key] = retries.get(key, 0) + 1
                time.sleep(min(30, 0.5 * 2 ** attempt) * random.uniform(0.5, 1.5))

    with ThreadPoolExecutor(max_workers=UPLOAD_WORKERS) as pool:
        list(pool.map(upload, range(OBJECT_COUNT)))
    return retries


@pytest.fixture
def client():
    client = storage.initialize_rustfs_client()
    yield client

    # Remove whatever the test left behind so repeated runs start clean
    base_name = storage.make_compliant_name(CAPTAIN_DOMAIN)
    storage.delete_bucket_users(storage.initialize_rustfs_admin_client(), base_name)
    for bucket_name in storage.find_buckets_containing(base_name, storage.list_buckets(client)):
        storage.delete_bucket(client, bucket_name)


def test_recreate_buckets_with_data(client):
    old_prefix, first_elapsed = _create_buckets()
    loki_bucket = f"{old_prefix}-loki"

    started = time.monotonic()
    retries = _upload_objects(loki_bucket)
    upload_elapsed = time.monotonic() - started

    uploaded = sum(1 for _ in client.list_objects(loki_bucket, recursive=True))
    assert uploaded == OBJECT_COUNT

    new_prefix, recreate_elapsed = _create_buckets()
    assert new_prefix != old_prefix

    for suffix in storage.BUCKET_SUFFIXES:
        assert not client.bucket_exists(f"{old_prefix}-{suffix}")
        assert client.bucket_exists(f"{new_prefix}-{suffix}")

    total_mib = OBJECT_COUNT * OBJECT_SIZE / (1024 * 1024)
    print(
        f"\n--- storage-buckets recreate timing ---\n"
        f"data:            {OBJECT_COUNT} objects x {OBJECT_SIZE / (1024 * 1024):g} MiB = {total_mib:g} MiB\n"
        f"first create:    {first_elapsed:.2f}s\n"
        f"upload:          {upload_elapsed:.2f}s ({total_mib / upload_elapsed:.1f} MiB/s)\n"
        f"upload retries:  {retries or 'none'}\n"
        f"recreate (full): {recreate_elapsed:.2f}s  <- delete phase alone is logged by the API as 'Deleted N bucket(s) in Xs'\n"
    )
