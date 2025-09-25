"""
This module provides functionality for querying and updating MongoDB collections,
with additional features for S3 storage and data processing.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.collection import Collection

from mongodb_upsert import upsert_items
from s3_utils import get_s3_client, get_s3_link

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def delete_items(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrapper function for deleting items from MongoDB.
    
    Args:
        event (Dict[str, Any]): A dictionary containing the items to be deleted.

    Returns:
        Dict[str, Any]: A dictionary containing the operation status.
    """

    database_name = event["database_name"]
    collection_name = event["collection_name"]
    items = event["items"]
    id_field = event.get("id_field", "_id")

    logger.info(f"Starting main function with database: {database_name}, collection: {collection_name}")
    collection = get_mongodb_collection(database_name, collection_name)
    logger.info(f"Retrieved MongoDB collection: {collection_name}")

    try:
        logger.info("Processing items")
        if isinstance(items, dict):
            items = [items]

        # logger.info(f"Deleting items from MongoDB")
        try:
            if id_field == '_id':
                # for item in items:
                #     collection.delete_one({id_field: item})
                result = collection.delete_many({'_id': {'$in': items}})

                logger.info("Items deleted successfully")
                return {
                    'statusCode': 200,
                    'body': json.dumps(f"{result.deleted_count} items deleted successfully")
                }
            else:
                # for item in items:
                #     result = collection.delete_many({id_field: item})
                result = collection.delete_many({id_field: {'$in': items}})

                logger.info("Items deleted successfully")
                return {
                    'statusCode': 200,
                    'body': json.dumps(f"{result.deleted_count} items deleted successfully")
                }

        except Exception as e:
            logger.error(f"Failed to delete items: {str(e)}")
            return {
                'statusCode': 400,
                'body': json.dumps(f"Failed to delete items: {str(e)}")
            }
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"An error occurred: {str(e)}")
        }

def upload_items(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrapper function for uploading items to MongoDB.

    Args:
        event (Dict[str, Any]): A dictionary containing the items to be uploaded.

    Returns:
        Dict[str, Any]: A dictionary containing the operation status.
    """

    database_name = event["database_name"]
    collection_name = event["collection_name"]
    items = event["items"]

    logger.info(f"Starting main function with database: {database_name}, collection: {collection_name}")
    collection = get_mongodb_collection(database_name, collection_name)
    logger.info(f"Retrieved MongoDB collection: {collection_name}")

    try:
        logger.info("Processing items")
        if isinstance(items, dict):  # Convert single item to a list
            items = [items]

        logger.info(f"Uploading {len(items)} items to MongoDB")
        try:
            result = collection.insert_many(items)  # Batch insert for efficiency
            logger.info("Items uploaded successfully")
            return {
                'statusCode': 200,
                'body': json.dumps(f"{len(result.inserted_ids)} items uploaded successfully")
            }
        except Exception as e:
            logger.error(f"Failed to upload items: {str(e)}")
            return {
                'statusCode': 400,
                'body': json.dumps(f"Failed to upload items: {str(e)}")
            }
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"An error occurred: {str(e)}")
        }

def get_mongodb_collection(database_name: str, collection_name: str, max_retries: int = 3, retry_delay: float = 2.0) -> Optional[Collection]:
    """
    Connect to MongoDB and return the specified collection, retrying if the connection fails.

    Args:
        database_name (str): The name of the database.
        collection_name (str): The name of the collection.
        max_retries (int): Maximum number of connection retries.
        retry_delay (float): Delay in seconds between retries.

    Returns:
        Optional[Collection]: The MongoDB collection object, or None if connection fails.
    """
    mongo_uri = os.environ.get("MONGODB_URI")
    if not mongo_uri:
        logger.error("MONGODB_URI environment variable is not set.")
        return None

    logger.info(f"Connecting to MongoDB with URI: {mongo_uri}")

    for attempt in range(max_retries):
        try:
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)  # 5-second timeout
            client.admin.command('ismaster')  # Check if server is available
            db = client[database_name]
            return db[collection_name]
        except Exception as e:
            logger.error(f"MongoDB connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logger.error("Exceeded maximum retry attempts. MongoDB connection failed.")
                return None

def _prepare_json_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare the JSON response.

    Args:
        response (Dict[str, Any]): The response data.

    Returns:
        Dict[str, Any]: The formatted JSON response.
    """
    logger.info("Preparing JSON response")
    # print(json.dumps(response, indent=4))

    def convert_nan_to_null(obj):
        if isinstance(obj, float) and np.isnan(obj):
            return None
        return obj

    def unescape_json(escaped_json_string):
        unescaped_string = re.sub(r'\\"', '"', escaped_json_string)
        return json.loads(unescaped_string)

    return {
        'statusCode': 200,
        'body': unescape_json(json.dumps(response, default=convert_nan_to_null)),
        'headers': {
            'Content-Type': 'application/json'
        }
    }
def upsert_wrapper(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrapper function for inserting or updating items in MongoDB.

    Args:
        event (Dict[str, Any]): A dictionary containing the items to be inserted or updated.

    Returns:
        Dict[str, Any]: A dictionary containing the operation status.
    """
    database_name = event["database_name"]
    collection_name = event["collection_name"]
    items = event["items"]
    id_field = event.get("id_field", "_id")
    
    logger.info(f"Starting main function with database: {database_name}, collection: {collection_name}")
    collection = get_mongodb_collection(database_name, collection_name)
    logger.info(f"Retrieved MongoDB collection: {collection_name}")
    
    try:
        logger.info("Processing items")
        if isinstance(items, dict):
            items = [items]
        
        logger.info(f"Inserting {len(items)} items into MongoDB")
        try:
            upsert_items(collection, items, id_field=id_field)
            logger.info("Items inserted successfully")
            return {
                'statusCode': 200,
                'body': json.dumps(f"{len(items)} items inserted successfully")
            }
        except Exception as e:
            logger.error(f"Failed to insert items: {str(e)}")
            return {
                'statusCode': 400,
                'body': json.dumps(f"Failed to insert items: {str(e)}")
            }
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"An error occurred: {str(e)}")
        }

def s3_link(event: Dict[str, Any]) -> Dict[str, Any]:
    bucket_name = event['bucket_name']
    object_name = event['object_name']

    AWS_ACCESS_KEY_ID_SELF = os.getenv("AWS_ACCESS_KEY_ID_SELF")
    AWS_SECRET_ACCESS_KEY_SELF = os.getenv("AWS_SECRET_ACCESS_KEY_SELF")
    region_name = os.getenv("AWS_REGION_SELF")
    s3_client = get_s3_client(AWS_ACCESS_KEY_ID_SELF, AWS_SECRET_ACCESS_KEY_SELF, region_name)

    link = get_s3_link(s3_client, bucket_name, object_name, expiry_seconds=7200)
    return {
        'statusCode': 200,
        'link': link
    }
