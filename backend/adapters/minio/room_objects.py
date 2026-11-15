"""Private, versioned Room8 uploads; verify streamed bytes, never trust ETag."""
from __future__ import annotations

import hashlib

from minio.error import S3Error

from backend.services.room_registration import PublicationFile
from render_engine.jobs.operation_logging import traced


@traced('catalog.register', 'private_bucket_check')
def private_bucket(client, bucket: str) -> None:
    if bucket not in ('burnroom-room-assets', 'burnroom-room-outputs'):
        raise ValueError('Dedicated private Room8 bucket required')
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    try:
        policy = client.get_bucket_policy(bucket)
    except S3Error as exc:
        if exc.code != 'NoSuchBucketPolicy':
            raise
    else:
        # Fail closed; do not rewrite an administrator's existing policy.
        if policy:
            raise ValueError('Room8 publication requires a bucket without a policy')


def verify_object(client, file: PublicationFile) -> None:
    stat = client.stat_object(file.bucket, file.key)
    if stat.size != file.size or stat.content_type != file.content_type:
        raise ValueError('Existing object size or media type differs; refusing overwrite')
    version = getattr(stat, 'version_id', None)
    response = client.get_object(file.bucket, file.key, **({'version_id': version} if version else {}))
    try:
        sha, size = hashlib.sha256(), 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > file.size:
                raise ValueError('Object exceeds expected size')
            sha.update(chunk)
        if size != file.size or sha.hexdigest() != file.sha256:
            raise ValueError('Remote SHA256 differs; refusing overwrite')
    finally:
        response.close()
        response.release_conn()


@traced('catalog.register', 'upload_and_readback')
def ensure_object(client, file: PublicationFile) -> dict:
    try:
        client.stat_object(file.bucket, file.key)
    except S3Error as exc:
        if exc.code not in ('NoSuchKey', 'NoSuchObject'):
            raise
        client.fput_object(file.bucket, file.key, str(file.path),
                           content_type=file.content_type, metadata={'sha256': file.sha256})
        reused = False
    else:
        reused = True
    verify_object(client, file)
    return {**file.summary(), 'reused_object': reused, 'upload_status': 'verified'}
