import uuid
from minio import Minio
from minio.error import S3Error
from minio.deleteobjects import DeleteObject
import re
import os
import glueops.setup_logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)

# ----------------------- Configuration ----------------------- #

# MinIO Server Configuration
MINIO_SERVER = "fsn1.your-objectstorage.com"  # Replace with your MinIO server
ACCESS_KEY = os.getenv("MINIO_S3_ACCESS_KEY_ID")               # Replace with your Access Key
SECRET_KEY = os.getenv("MINIO_S3_SECRET_KEY")                  # Replace with your Secret Key
MINIO_REGION = "fsn1"                         # Replace with your region
USE_SSL = True                                # Set to False if not using SSL

# Bucket Configuration
UUID_LENGTH = 4                               # Length of UUID suffix (adjust as needed)
UUID_FORMAT = 'hex'                            # Format of UUID ('hex' for hexadecimal)

# ----------------------- Functions ----------------------- #

def initialize_minio_client():
    """
    Initializes and returns a MinIO client.
    """
    try:
        client = Minio(
            MINIO_SERVER,
            access_key=ACCESS_KEY,
            secret_key=SECRET_KEY,
            secure=USE_SSL,
            region=MINIO_REGION
        )
        return client
    except Exception as e:
        logger.error(f"Failed to initialize MinIO client: {e}")
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


def parameterize_storage_config(bucket_prefix):
    """
    Parameterizes the storage configuration template with the correct bucket names.
    
    Args:
        template (str): The storage configuration template.
        bucket_prefix (str): The prefix for the buckets.
    
    Returns:
        str: The parameterized storage configuration.
    """
    # Example usage
    template = """
      loki_storage         = <<EOT
bucketNames:
        chunks: {loki_bucket}
        ruler: {loki_bucket}
        admin: {loki_bucket}
   type: s3
   s3:
      s3: {loki_bucket}
      endpoint: https://{region}.your-objectstorage.com
      region: us-east-1
      accessKeyId: {access_key}
      secretAccessKey: {secret_key}
      s3ForcePathStyle: false
      insecure: false
    EOT
      thanos_storage       = <<EOT
type: s3
    config:
        bucket: {thanos_bucket}
        endpoint: {region}.your-objectstorage.com
        access_key: {access_key}
        secret_key: {secret_key}
EOT
      tempo_storage        = <<EOT
backend: s3
    s3:
        access_key: {access_key}
        secret_key: {secret_key}
        bucket:  {tempo_bucket}
        endpoint: {region}.your-objectstorage.com
        insecure: false
EOT
    """

    return template.format(
        loki_bucket=f"{bucket_prefix}-loki",
        thanos_bucket=f"{bucket_prefix}-thanos",
        tempo_bucket=f"{bucket_prefix}-tempo",
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        region=MINIO_REGION
    )



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
        client (Minio): The MinIO client instance.
    
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
        client (Minio): The MinIO client instance.
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
        client (Minio): The MinIO client instance.
        bucket_name (str): The name of the bucket to delete.
    """
    # Delete all objects in the bucket
    #logger.info(f"Deleting all objects in bucket '{bucket_name}'...")
    #delete_all_objects(client, bucket_name)
    
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
        client (Minio): The MinIO client instance.
        bucket_name (str): The base name of the buckets to create.
    
    Returns:
        str: The base name of the buckets created.
    """
    suffixes = ["tempo", "loki", "thanos"]
    try:
        for suffix in suffixes:
            full_bucket_name = f"{bucket_name}-{suffix}"
            client.make_bucket(full_bucket_name)
            logger.info(f"Bucket '{full_bucket_name}' created successfully.")
        return bucket_name
    except S3Error as e:
        logger.info(f"Error creating bucket '{full_bucket_name}': {e}")
        raise

def create_all_buckets(captain_domain):
    """
    Manages buckets by deleting existing ones containing the base name and creating a new unique bucket.
    """
    # Initialize MinIO client
    client = initialize_minio_client()
    
    # List all buckets
    logger.info("Listing all existing buckets...")
    buckets = list_buckets(client)
    
    # Find buckets containing the base name
    base_bucket_name = make_compliant_name(captain_domain)
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
    parameterized_config = parameterize_storage_config(bucket_prefix)
    return parameterized_config

