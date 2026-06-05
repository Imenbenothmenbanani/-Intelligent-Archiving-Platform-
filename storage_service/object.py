import sys
from pathlib import Path

# Ensure config/ is on the path regardless of where this module is imported from
sys.path.insert(0, str(Path(__file__).parent / "config"))
sys.path.insert(0, str(Path(__file__).parent))

from config import get_client
from io import BytesIO
from botocore.exceptions import ClientError

def upload_file(bucket, file_path, object_name):
    try:
        client = get_client()
        with open(file_path, "rb") as f:
            client.put_object(
                Bucket=bucket,
                Key=object_name,
                Body=f
            )
        return f"{object_name} uploaded to {bucket}"
    except (ClientError, FileNotFoundError) as e:
        return f"Upload failed: {str(e)}"

def list_files(bucket):
    try:
        client = get_client()
        response = client.list_objects_v2(Bucket=bucket)
        if "Contents" not in response:
            return []
        return [obj["Key"] for obj in response["Contents"]]
    except ClientError as e:
        return f"Error listing files: {e.response['Error']['Message']}"

def delete_file(bucket, object_name):
    try:
        client = get_client()
        client.delete_object(Bucket=bucket, Key=object_name)
        return f"{object_name} deleted."
    except ClientError as e:
        return f"Delete failed: {e.response['Error']['Message']}"

def get_file_metadata(bucket, object_name):
    try:
        client = get_client()
        response = client.head_object(Bucket=bucket, Key=object_name)
        return {
            "size": response.get("ContentLength"),
            "content_type": response.get("ContentType"),
            "last_modified": str(response.get("LastModified")),
            "etag": response.get("ETag"),
            "user_metadata": response.get("Metadata", {}),
        }
    except ClientError as e:
        return f"Metadata retrieval failed: {e.response['Error']['Message']}"

def get_file_stream(bucket: str, object_name: str):
    """Retrieve file as memory stream efficiently."""
    try:
        client = get_client()
        response = client.get_object(Bucket=bucket, Key=object_name)
        return BytesIO(response["Body"].read())
    except ClientError as e:
        print(f"Streaming failed: {e}")
        return None