import io
import json
import os
import time
import uuid
from datetime import datetime, timedelta

import boto3
import pandas as pd
from botocore.exceptions import ClientError
from tqdm import tqdm


def get_s3_client(AWS_ACCESS_KEY_ID_SELF, AWS_SECRET_ACCESS_KEY_SELF, region_name):
    return boto3.client('s3',
                        aws_access_key_id=AWS_ACCESS_KEY_ID_SELF,
                        aws_secret_access_key=AWS_SECRET_ACCESS_KEY_SELF,
                        region_name=region_name)

def create_bucket_if_not_exists(s3_client, bucket_name, region_name):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"Bucket '{bucket_name}' already exists.")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            try:
                s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': region_name}
                )
                print(f"Bucket '{bucket_name}' created successfully.")
            except ClientError as create_error:
                print(f"Error creating bucket: {create_error}")
                return False
        else:
            print(f"Error checking bucket: {e}")
            return False
    return True

def upload_to_s3_and_get_link(s3_client, bucket_name, file_path, object_name=None, expiry_seconds=7200):
    if object_name is None:
        object_name = os.path.basename(file_path)

    s3_client.upload_file(file_path, bucket_name, object_name)

    url = get_s3_link(s3_client, bucket_name, object_name, expiry_seconds=expiry_seconds)  # 2 hours
    return url

def upload_data_to_s3_and_get_link(s3_client, bucket_name, data, object_name, expiry_seconds=7200):
    if isinstance(data, dict):
        # Convert the dictionary to a JSON string
        json_data = json.dumps(data)
        file_like_object = io.BytesIO(json_data.encode('utf-8'))
    elif isinstance(data, pd.DataFrame):
        # Convert the DataFrame to a CSV string
        csv_buffer = io.StringIO()
        data.to_csv(csv_buffer, index=False)
        file_like_object = io.BytesIO(csv_buffer.getvalue().encode('utf-8'))
    elif isinstance(data, bytes):
        # Convert the DataFrame to a CSV string
        file_like_object = io.BytesIO(data)
    else:
        raise ValueError("Unsupported data type")

    s3_client.upload_fileobj(file_like_object, bucket_name, object_name)
    
    url = get_s3_link(s3_client, bucket_name, object_name, expiry_seconds=expiry_seconds)  # 2 hours
    
    return url

def list_objects(s3_client, bucket_name):
    response = s3_client.list_objects_v2(Bucket=bucket_name)
    return [obj['Key'] for obj in response.get('Contents', [])]

def delete_object(s3_client, bucket_name, object_name):
    s3_client.delete_object(Bucket=bucket_name, Key=object_name)

def get_s3_link(s3_client, bucket_name, object_name, expiry_seconds=7200):
    url = s3_client.generate_presigned_url('get_object',
                                           Params={'Bucket': bucket_name,
                                                   'Key': object_name},
                                           ExpiresIn=expiry_seconds)
    return url

def upload_images_and_save_urls(s3_client, bucket_name, png_files, output_json_path):
    if os.path.exists(output_json_path):
        with open(output_json_path, 'r') as json_file:
            url_file_pairs = json.load(json_file)
    else:
        url_file_pairs = {}

    for file_path in tqdm(png_files):
        original_file_name = file_path
        if original_file_name in url_file_pairs:
            print(f"Skipping {original_file_name} as it has already been uploaded")
            continue
        
        # Generate a unique ID for the image
        image_id = str(uuid.uuid4())
        
        # Use the image_id as the object name
        object_name = f"{image_id}.png"
        
        shareable_link = upload_to_s3_and_get_link(s3_client, bucket_name, file_path, object_name)
        url_file_pairs[original_file_name] = {
            "original_file_name": original_file_name,
            "url": shareable_link,
            "id": image_id,
            "object_name": object_name
        }
        time.sleep(0.03)
    
    with open(output_json_path, 'w') as json_file:
        json.dump(url_file_pairs, json_file, indent=2)
    
    print(f"Uploaded {len(url_file_pairs)} images and saved URL-file pairs with IDs to {output_json_path}")

def find_object(s3_client, bucket_name, object_name):
    try:
        s3_client.head_object(Bucket=bucket_name, Key=object_name)
        return True
    except ClientError:
        return False

if __name__ == "__main__":
    pass