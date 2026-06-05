import boto3
import os
from pathlib import Path
from botocore.client import Config
from dotenv import load_dotenv

# Load .env from the config folder regardless of where the app is run from
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

ACCESS_KEY = os.getenv("CEPH_ACCESS_KEY")
SECRET_KEY = os.getenv("CEPH_SECRET_KEY")
ENDPOINT = os.getenv("CEPH_ENDPOINT")
REGION = os.getenv("CEPH_REGION", "us-east-1") 

def get_client():
    """Initializes the S3 client only when called."""
    if not all([ACCESS_KEY, SECRET_KEY, ENDPOINT]):
        raise EnvironmentError("Missing Ceph configuration environment variables.")
        
    return boto3.client(
        's3',
        endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name=REGION
    )