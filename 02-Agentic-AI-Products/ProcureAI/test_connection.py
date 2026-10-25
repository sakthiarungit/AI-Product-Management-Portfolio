import os
import libsql
from dotenv import load_dotenv

# Step 1: Load environment variables from .env
load_dotenv()

# Step 2: Read the Turso connection settings
database_url = os.getenv("TURSO_DATABASE_URL")
auth_token = os.getenv("TURSO_AUTH_TOKEN")

# Step 3: Validate required configuration
if not database_url or not auth_token:
    raise ValueError("Missing Turso database URL or authentication token")

# Step 4: Establish connection to the cloud database
connection = libsql.connect(
    database=database_url,
    auth_token=auth_token
)

try:
    # Step 5: Execute a simple SQL query
    cursor = connection.execute("SELECT 1")

    # Step 6: Retrieve the result
    result = cursor.fetchone()

    print("Turso Cloud connection successful!")
    print("SQL query result:", result[0])

finally:
    # Step 7: Close the connection
    connection.close()