from loguru import logger

from api.constants import (
    ENABLE_AWS_S3,
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_PUBLIC_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    S3_BUCKET,
    S3_REGION,
)
from api.enums import StorageBackend

from .filesystem import BaseFileSystem, MinioFileSystem, S3FileSystem


def get_storage_for_backend(backend: str) -> BaseFileSystem:
    """Get storage instance for a specific backend enum.

    Maps StorageBackend enum codes to actual storage implementations:
    - Code 1 (S3): AWS S3 via S3FileSystem
    - Code 2 (MINIO): MinIO via MinioFileSystem
    """
    # Code 2: MinIO implementation (local/OSS deployments)
    if backend == StorageBackend.MINIO.value:
        endpoint = MINIO_ENDPOINT
        # Auto-detect public endpoint:
        # - If MINIO_PUBLIC_ENDPOINT is set, use it (for custom domains/IPs)
        # - If running in Docker and endpoint is "minio:9000", use "localhost:9000" for local dev
        # - Otherwise, use the endpoint as-is (both containers and browser can reach it)
        public_endpoint = MINIO_PUBLIC_ENDPOINT
        if not public_endpoint:
            # Auto-detect based on endpoint
            if endpoint.startswith("minio:"):
                # Docker internal endpoint detected, assume local development
                public_endpoint = endpoint.replace("minio:", "localhost:")
                logger.info(
                    f"Auto-detected local development: using {public_endpoint} for public access"
                )
            elif endpoint.startswith("host.docker.internal:"):
                # Docker Desktop special DNS detected, use localhost for browser access
                public_endpoint = endpoint.replace(
                    "host.docker.internal:", "localhost:"
                )
                logger.info(
                    f"Auto-detected Docker Desktop: using {public_endpoint} for public access"
                )
            else:
                # Already using a public endpoint (localhost:9000 or domain:9000)
                public_endpoint = endpoint

        access_key = MINIO_ACCESS_KEY
        secret_key = MINIO_SECRET_KEY
        bucket = MINIO_BUCKET
        secure = MINIO_SECURE
        logger.info(
            f"Initializing {backend} storage at {endpoint} (public: {public_endpoint}) with bucket '{bucket}'"
        )
        return MinioFileSystem(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket_name=bucket,
            secure=secure,
            public_endpoint=public_endpoint,
        )

    # Code 1: AWS S3 implementation (cloud deployments)
    elif backend == StorageBackend.S3.value:
        if not S3_BUCKET:
            raise ValueError(
                "S3_BUCKET environment variable is required when using S3 storage"
            )
        bucket = S3_BUCKET
        region = S3_REGION
        logger.info(
            f"Initializing {backend} storage with bucket '{bucket}' in region '{region}'"
        )
        return S3FileSystem(bucket, region)

    # Future backend implementations can be added here:
    # elif backend == StorageBackend.GCS:  # Code 3
    #     return GoogleCloudFileSystem(...)
    # elif backend == StorageBackend.AZURE:  # Code 4
    #     return AzureBlobFileSystem(...)

    else:
        raise ValueError(f"Unknown storage backend: {backend}")


def get_current_storage_backend() -> StorageBackend:
    """Get the current storage backend enum."""
    return StorageBackend.get_current_backend()


# Create a single storage instance at module load time
_backend = StorageBackend.get_current_backend()
logger.info(
    f"Initializing storage backend: {_backend.name} (value: {_backend.value}, ENABLE_AWS_S3={ENABLE_AWS_S3})"
)
storage_fs = get_storage_for_backend(_backend.value)


# For backward compatibility, keep get_storage() function
def get_storage() -> BaseFileSystem:
    """Get the module-level storage instance.

    Deprecated: Use 'from api.services.storage import storage_fs' instead.
    """
    return storage_fs
