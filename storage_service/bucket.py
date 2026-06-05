import sys
from pathlib import Path

# Ensure config/ is on the path regardless of where this module is imported from
sys.path.insert(0, str(Path(__file__).parent / "config"))
sys.path.insert(0, str(Path(__file__).parent))

from config import get_client
from botocore.exceptions import ClientError

def create_bucket(bucket_name: str):
    try:
        client = get_client() # Lazy initialization
        client.create_bucket(Bucket=bucket_name)
        return f"Bucket '{bucket_name}' created."
    except ClientError as e:
        return f"Error creating bucket: {e.response['Error']['Message']}"

def list_buckets():
    try:
        client = get_client()
        response = client.list_buckets()
        return [b["Name"] for b in response["Buckets"]]
    except ClientError as e:
        return f"Error listing buckets: {e.response['Error']['Message']}"

def delete_bucket(bucket_name: str):
    try:
        client = get_client()
        client.delete_bucket(Bucket=bucket_name)
        return f"Bucket '{bucket_name}' deleted."
    except ClientError as e:
        return f"Error deleting bucket: {e.response['Error']['Message']}"