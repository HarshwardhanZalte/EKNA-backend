import boto3
from django.conf import settings
from botocore.client import Config
import uuid

def get_s3_client():
    # Configure client for MinIO or AWS S3 depending on settings
    client = boto3.client(
        's3',
        region_name=getattr(settings, 'AWS_S3_REGION_NAME', None),
        aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
        aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
        endpoint_url=getattr(settings, 'AWS_S3_ENDPOINT_URL', None),
        config=Config(signature_version="s3v4", s3={"addressing_style":"path"}),
        use_ssl=getattr(settings, 'AWS_S3_USE_SSL', False)
    )
    return client


def upload_fileobj_to_s3(file_obj, bucket_name, key, extra_args=None):
    client = get_s3_client()
    extra_args = extra_args or {}
    
    # upload_fileobj streams the file to S3
    client.upload_fileobj(Fileobj=file_obj, Bucket=bucket_name, Key=key, ExtraArgs=extra_args)
    
    endpoint = getattr(settings, "AWS_S3_ENDPOINT_URL", None)
    if endpoint:
        endpoint = endpoint.rstrip('/')
        # For MinIO path-style: {endpoint}/{bucket}/{key}
        return f"{endpoint}/{bucket_name}/{key}"
    else:
        # AWS default url (public)
        region = getattr(settings, "AWS_S3_REGION_NAME", "us-east-1")
        return f"https://{bucket_name}.s3.{region}.amazonaws.com/{key}"
    
    
def generate_s3_key(filename):
    # Unique key: use uuid + original filename to keep extension
    ext = ""
    if "." in filename:
        ext = filename.split('.')[-1]
    unique = uuid.uuid4().hex
    if ext:
        return f"documents/{unique}.{ext}"
    return f"documents/{unique}"
