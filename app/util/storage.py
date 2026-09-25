import hashlib
import json
import secrets
import uuid
from Crypto.Cipher import AES
from minio import Minio
from minio import crypto as minio_crypto
from minio.credentials import StaticProvider
from minio.minioadmin import MinioAdmin
from minio.error import S3Error
from minio.deleteobjects import DeleteObject
import re
import os
import yaml
import glueops.setup_logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)

# ----------------------- RustFS admin crypto compat ----------------------- #

# minio-py only decrypts admin responses encrypted with AEAD IDs 0/1 (Argon2id key).
# FIPS builds of RustFS answer with ID 2: the same stream format, but with a
# PBKDF2-SHA256 (8192 iterations) key and AES-GCM. Teach minio-py about ID 2.
_PBKDF2_AES_GCM_ID = 2
_minio_get_cipher = minio_crypto._get_cipher


def _get_cipher(aead_id, key, nonce):
    if aead_id == _PBKDF2_AES_GCM_ID:
        return AES.new(key, AES.MODE_GCM, nonce)
    return _minio_get_cipher(aead_id, key, nonce)


class _DecryptReader(minio_crypto.DecryptReader):
    def __init__(self, response, secret):
        self._response = response
        self._secret = secret
        self._payload = None

        header = self._response.read(41)
        if len(header) != 41:
            raise IOError("insufficient data")
        self._salt = header[:32]
        self._aead_id = header[32]
        self._nonce = header[33:]
        if self._aead_id == _PBKDF2_AES_GCM_ID:
            self._key = hashlib.pbkdf2_hmac("sha256", self._secret, self._salt, 8192, 32)
        else:
            self._key = minio_crypto._generate_key(self._secret, self._salt)
        padded_nonce = self._nonce + b"\x00\x00\x00\x00"
        self._additional_data = minio_crypto._generate_additional_data(
            self._aead_id, self._key, padded_nonce
        )
        self._chunk = b""
        self._count = 0
        self._is_closed = False


minio_crypto._get_cipher = _get_cipher
minio_crypto.DecryptReader = _DecryptReader

# ----------------------- Configuration ----------------------- #

# RustFS Server Configuration (S3-compatible, accessed via the MinIO client)
# These must be admin credentials: they manage buckets and the per-bucket IAM users.
RUSTFS_ENDPOINT = os.getenv("RUSTFS_ENDPOINT")                 # Host[:port] only, e.g. rustfs.glueopshosted.rocks
ACCESS_KEY = os.getenv("RUSTFS_ACCESS_KEY_ID")
SECRET_KEY = os.getenv("RUSTFS_SECRET_KEY")
RUSTFS_REGION = os.getenv("RUSTFS_REGION", "us-east-1")        # RustFS default region
USE_SSL = os.getenv("RUSTFS_USE_SSL", "true").lower() != "false"

# Bucket Configuration
UUID_LENGTH = 4                               # Length of UUID suffix (adjust as needed)
UUID_FORMAT = 'hex'                            # Format of UUID ('hex' for hexadecimal)
BUCKET_SUFFIXES = ["tempo", "loki", "thanos"]  # One bucket (and IAM user) per suffix

# ----------------------- Functions ----------------------- #

def initialize_rustfs_client():
    """
    Initializes and returns a MinIO client pointed at RustFS.
    """
    try:
        client = Minio(
            RUSTFS_ENDPOINT,
            access_key=ACCESS_KEY,
            secret_key=SECRET_KEY,
            secure=USE_SSL,
            region=RUSTFS_REGION
        )
        return client
    except Exception as e:
        logger.error(f"Failed to initialize RustFS client: {e}")
        raise


def initialize_rustfs_admin_client():
    """
    Initializes and returns a MinIO admin client pointed at RustFS (used for IAM).
    """
    try:
        return MinioAdmin(
            endpoint=RUSTFS_ENDPOINT,
            credentials=StaticProvider(ACCESS_KEY, SECRET_KEY),
            region=RUSTFS_REGION,
            secure=USE_SSL,
        )
    except Exception as e:
        logger.error(f"Failed to initialize RustFS admin client: {e}")
        raise


def make_compliant_name(name: str) -> str:
    # Remove invalid characters (anything not lowercase letters, numbers, or hyphens)
    name = re.sub(r'[^a-z0-9\-]', '', name.lower())
    
    # Ensure it starts with a letter or number by stripping leading hyphens
    name = re.sub(r'^-+', '', name)
    
    # Ensure it ends with a letter or number by stripping trailing hyphens
    name = re.sub(r'-+$', '', name)
    
    # If the name is now empty, return a default compliant name
    return name if name else "default-name"


def parameterize_storage_config(bucket_prefix, credentials):
    """
    Builds the loki/thanos/tempo storage config as three terraform heredoc
    assignments ready to paste into a tenant's `cluster_environments` block.

    The YAML for each heredoc is generated from a dict via ``yaml.safe_dump`` so
    it is always valid, consistently-indented, standard YAML. The consuming
    platform chart normalizes indentation (yamldecode/yamlencode/indent), so the
    exact indentation emitted here is not load-bearing.

    Args:
        bucket_prefix (str): The prefix for the buckets.
        credentials (dict): Maps each bucket suffix ("loki", "thanos", "tempo")
            to the (access_key, secret_key) of the IAM user scoped to that bucket.

    Returns:
        str: The parameterized storage configuration.
    """
    endpoint_host = RUSTFS_ENDPOINT
    scheme = "https" if USE_SSL else "http"
    loki_access_key, loki_secret_key = credentials["loki"]
    thanos_access_key, thanos_secret_key = credentials["thanos"]
    tempo_access_key, tempo_secret_key = credentials["tempo"]

    loki_storage = {
        "bucketNames": {
            "chunks": f"{bucket_prefix}-loki",
            "ruler": f"{bucket_prefix}-loki",
            "admin": f"{bucket_prefix}-loki",
        },
        "type": "s3",
        "s3": {
            "s3": f"{bucket_prefix}-loki",
            "endpoint": f"{scheme}://{endpoint_host}",
            "region": RUSTFS_REGION,
            "accessKeyId": loki_access_key,
            "secretAccessKey": loki_secret_key,
            "s3ForcePathStyle": True,
            "insecure": not USE_SSL,
        },
    }
    thanos_storage = {
        "type": "s3",
        "config": {
            "bucket": f"{bucket_prefix}-thanos",
            "endpoint": endpoint_host,
            "region": RUSTFS_REGION,
            "access_key": thanos_access_key,
            "secret_key": thanos_secret_key,
            "insecure": not USE_SSL,
            "bucket_lookup_type": "path",
        },
    }
    tempo_storage = {
        "backend": "s3",
        "s3": {
            "access_key": tempo_access_key,
            "secret_key": tempo_secret_key,
            "bucket": f"{bucket_prefix}-tempo",
            "endpoint": endpoint_host,
            "region": RUSTFS_REGION,
            "insecure": not USE_SSL,
            "forcepathstyle": True,
        },
    }

    return "".join(
        f"      {name} = <<EOT\n{_render_storage_yaml(value)}\nEOT\n"
        for name, value in (
            ("loki_storage", loki_storage),
            ("thanos_storage", thanos_storage),
            ("tempo_storage", tempo_storage),
        )
    )


def _render_storage_yaml(value):
    """Serialize a storage-config dict to clean, block-style YAML.

    ``sort_keys=False`` preserves the readable field order above; ``width`` is
    large so long secret/endpoint values are never line-wrapped (a wrapped line
    would corrupt the pasted heredoc).
    """
    return yaml.safe_dump(
        value,
        default_flow_style=False,
        sort_keys=False,
        width=4096,
    ).strip()



def generate_unique_bucket_name(base_name, length=UUID_LENGTH, fmt=UUID_FORMAT):
    """
    Generates a unique bucket name by appending a unique suffix to the base name.
    
    Args:
        base_name (str): The base name of the bucket.
        length (int): The length of the UUID suffix.
        fmt (str): The format of the UUID ('hex', 'urn', etc.).
    
    Returns:
        str: The generated unique bucket name.
    """
    if fmt == 'hex':
        suffix = uuid.uuid4().hex[:length]
    elif fmt == 'urn':
        suffix = str(uuid.uuid4())[:length]
    else:
        suffix = uuid.uuid4().hex[:length]  # Default to hex
    return f"{base_name}-{suffix}"

def list_buckets(client):
    """
    Retrieves and returns a list of all buckets.
    
    Args:
        client (Minio): The MinIO client instance connected to RustFS.
    
    Returns:
        list: A list of bucket objects.
    """
    try:
        buckets = client.list_buckets()
        return buckets
    except S3Error as e:
        logger.error(f"Error listing buckets: {e}")
        raise

def find_buckets_containing(base_name, buckets):
    """
    Identifies and returns a list of bucket names that contain the base name.
    
    Args:
        base_name (str): The base name to search for within bucket names.
        buckets (list): A list of bucket objects.
    
    Returns:
        list: A list of bucket names containing the base name.
    """
    matching_buckets = [bucket.name for bucket in buckets if base_name in bucket.name]
    return matching_buckets

def delete_all_objects(client, bucket_name):
    """
    Deletes all objects within the specified bucket.
    
    Args:
        client (Minio): The MinIO client instance connected to RustFS.
        bucket_name (str): The name of the bucket from which to delete objects.
    """
    try:
        objects = client.list_objects(bucket_name, recursive=True)
        objects_to_delete = (DeleteObject(obj.object_name) for obj in objects)
        delete_results = client.remove_objects(bucket_name, objects_to_delete)
        for result in delete_results:
            if result.status_code == 204:
                logger.info(f"Deleted object: {result.object_name}")
            elif result.status_code != 204:
                logger.error(f"Failed to delete object: {result.object_name}, Status Code: {result.status_code}")
    except S3Error as e:
        logger.error(f"Error deleting objects in bucket '{bucket_name}': {e}")
        raise

def delete_bucket(client, bucket_name):
    """
    Deletes the specified bucket after removing all its contents.
    
    Args:
        client (Minio): The MinIO client instance connected to RustFS.
        bucket_name (str): The name of the bucket to delete.
    """
    # Delete all objects in the bucket
    #logger.info(f"Deleting all objects in bucket '{bucket_name}'...")
    delete_all_objects(client, bucket_name)
    
    try:
        # Remove the bucket
        client.remove_bucket(bucket_name)
        logger.info(f"Bucket '{bucket_name}' has been deleted successfully.")
    except S3Error as e:
        logger.error(f"Error removing bucket '{bucket_name}': {e}")
        raise

def create_bucket(client, bucket_name):
    """
    Creates new buckets with the specified name and suffixes.
    
    Args:
        client (Minio): The MinIO client instance connected to RustFS.
        bucket_name (str): The base name of the buckets to create.
    
    Returns:
        str: The base name of the buckets created.
    """
    try:
        for suffix in BUCKET_SUFFIXES:
            full_bucket_name = f"{bucket_name}-{suffix}"
            client.make_bucket(full_bucket_name)
            logger.info(f"Bucket '{full_bucket_name}' created successfully.")
        return bucket_name
    except S3Error as e:
        logger.info(f"Error creating bucket '{full_bucket_name}': {e}")
        raise

def create_bucket_user(admin, bucket_name):
    """
    Creates an IAM user with a policy granting access to a single bucket only.

    The policy is named after the bucket, which is how stale users are found
    again by ``delete_bucket_users``. The access key is random because names
    derived from the captain domain can exceed access key length limits.

    Args:
        admin (MinioAdmin): The MinIO admin client instance connected to RustFS.
        bucket_name (str): The bucket the user is scoped to.

    Returns:
        tuple: The (access_key, secret_key) of the created user.
    """
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:*"],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*",
                ],
            }
        ],
    }
    access_key = secrets.token_hex(10)
    secret_key = secrets.token_hex(20)
    try:
        admin.policy_add(bucket_name, policy=policy)
        admin.user_add(access_key, secret_key)
        admin.attach_policy([bucket_name], user=access_key)
        logger.info(f"IAM user '{access_key}' created for bucket '{bucket_name}'.")
        return access_key, secret_key
    except Exception as e:
        logger.error(f"Error creating IAM user for bucket '{bucket_name}': {e}")
        raise

def delete_bucket_users(admin, base_name):
    """
    Deletes the IAM users and policies previously created for buckets containing the base name.

    Args:
        admin (MinioAdmin): The MinIO admin client instance connected to RustFS.
        base_name (str): The base name to search for within policy names.
    """
    try:
        users = json.loads(admin.user_list() or "{}")
        for access_key, info in users.items():
            if base_name in (info.get("policyName") or ""):
                admin.user_remove(access_key)
                logger.info(f"Deleted IAM user '{access_key}' ({info.get('policyName')}).")

        policies = json.loads(admin.policy_list() or "{}")
        for policy_name in policies:
            if base_name in policy_name:
                admin.policy_remove(policy_name)
                logger.info(f"Deleted IAM policy '{policy_name}'.")
    except Exception as e:
        logger.error(f"Error deleting IAM users for '{base_name}': {e}")
        raise

def create_all_buckets(captain_domain):
    """
    Manages buckets by deleting existing ones containing the base name and creating a new unique bucket.
    """
    # Initialize RustFS clients
    client = initialize_rustfs_client()
    admin = initialize_rustfs_admin_client()
    
    # List all buckets
    logger.info("Listing all existing buckets...")
    buckets = list_buckets(client)
    
    # Find buckets containing the base name
    base_bucket_name = make_compliant_name(captain_domain)

    # Delete IAM users/policies of the previous buckets
    delete_bucket_users(admin, base_bucket_name)

    matching_buckets = find_buckets_containing(base_bucket_name, buckets)
    
    # Delete each matching bucket
    if matching_buckets:
        logger.info(f"Found {len(matching_buckets)} bucket(s) containing '{base_bucket_name}'. Deleting them...")
        for bucket_name in matching_buckets:
            delete_bucket(client, bucket_name)
    else:
        logger.info(f"No existing buckets contain the base name '{base_bucket_name}'.")
    
    # Generate a unique bucket name
    unique_bucket_name = generate_unique_bucket_name(base_bucket_name)
    logger.info(f"Generated unique bucket name: {unique_bucket_name}")
    
    # Create the new bucket
    bucket_prefix = create_bucket(client, unique_bucket_name)
    logger.info(f"Buckets created with prefix: {bucket_prefix}")

    # Create one IAM user per bucket, scoped to that bucket only
    credentials = {
        suffix: create_bucket_user(admin, f"{bucket_prefix}-{suffix}")
        for suffix in BUCKET_SUFFIXES
    }
    parameterized_config = parameterize_storage_config(bucket_prefix, credentials)
    return parameterized_config

