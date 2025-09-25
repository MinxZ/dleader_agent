import hashlib
import random
import time


def generate_unique_id():
    """
    Generates a unique ID.

    This function uses the current time in seconds since the Unix epoch,
    combined with a random integer between 1000 and 9999, to create a
    unique string. Optionally, it hashes this string to create a fixed-length
    unique ID.

    Returns:
        str: The unique ID as a string.
    """
    # Get the current time in seconds since epoch
    current_time = time.time()

    # Add some randomness (e.g., random integer)
    random_value = random.randint(1000, 9999)

    # Combine them to create a unique string
    unique_string = f"{current_time}-{random_value}"

    # Optionally, hash it to create a fixed-length unique ID, make it 32
    unique_id = hashlib.sha256(unique_string.encode()).hexdigest()

    # Optionally, truncate the hash to a fixed length
    unique_id = unique_id[:16]

    return unique_id

if __name__ == "__main__":
    unique_id = generate_unique_id()
    print(unique_id, len(unique_id))
