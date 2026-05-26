import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    \"\"\"Unified configuration variables loaded from environment.\"\"\"
    
    # GCP / BigQuery
    GCP_PROJECT_ID = os.getenv(\"GCP_PROJECT_ID\", \"your-gcp-project-id\")
    BQ_DATASET_NAME = os.getenv(\"BQ_DATASET_NAME\", \"weather_station\")
    
    # Coordinates for Weather
    LATITUDE = os.getenv(\"LATITUDE\", \"46.5197\") # Default to Lausanne
    LONGITUDE = os.getenv(\"LONGITUDE\", \"6.6323\")
    
    # API Keys
    OPENWEATHERMAP_API_KEY = os.getenv(\"OPENWEATHERMAP_API_KEY\", \"\")
    OPENAI_API_KEY = os.getenv(\"OPENAI_API_KEY\", \"\")

    # Backend
    API_PORT = int(os.getenv(\"PORT\", 8080))
