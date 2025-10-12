import datetime

from pymongo import MongoClient, UpdateOne


def upsert_items(collection, data, id_field='UniProtKBID'):
    """
    Upsert items in a MongoDB collection.

    Parameters
    ----------
    collection : pymongo.collection.Collection
        The MongoDB collection to upsert into.
    data : list
        A list of dictionaries, where each dictionary is an item to be upserted.
        Each dictionary should have a key matching the specified `id_field`.
    id_field : str
        The field of the item to use as the MongoDB document _id.

    Returns
    -------
    None

    Notes
    -----
    If the list of items is 3 or less, this function will perform a single upsert
    for each item. If the list of items is greater than 3, this function will
    use the bulk_write method to upsert all items in a single operation.
    """
    if len(data) > 3:
        bulk_operations = []
        for item in data:
            current_time = datetime.datetime.now(datetime.UTC).timestamp()
            # Use the specified field as _id
            if id_field != '_id':
                item['_id'] = item[id_field]
            item_with_last_updated = item.copy()
            item_with_last_updated['lastUpdated'] = current_time            
            
            # Create an UpdateOne operation for each item
            bulk_operations.append(
                UpdateOne(
                    {"_id": item['_id']},
                    {"$set": item_with_last_updated},
                    upsert=True
                )
            )
        
        # Execute the bulk write operation
        result = collection.bulk_write(bulk_operations)
        print(f"{result.upserted_count} items have been inserted in MongoDB.")
        print(f"{result.modified_count} items have been updated in MongoDB.")
    else:
        for item in data:
            current_time = datetime.datetime.now(datetime.UTC).timestamp()
            # Use the specified field as _id
            if id_field != '_id':
                item['_id'] = item[id_field]
            item_with_last_updated = item.copy()
            item_with_last_updated['lastUpdated'] = current_time            

            # Upsert the document
            result = collection.update_one(
                {"_id": item['_id']},
                {"$set": item_with_last_updated},
                upsert=True
            )
            
            if result.upserted_id:
                print(f"item {item['_id']} has been successfully inserted in MongoDB.")
            elif result.modified_count > 0:
                print(f"item {item['_id']} has been successfully updated in MongoDB.")
            else:
                print(f"item {item['_id']} has not been updated in MongoDB.")

if __name__ == '__main__':
    pass