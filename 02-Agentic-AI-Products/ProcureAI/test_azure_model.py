import os

from dotenv import load_dotenv
from openai import OpenAI
from azure.identity import (
    AzureCliCredential,
    get_bearer_token_provider,
)

load_dotenv(override=True)

endpoint = os.environ["AZURE_OPENAI_BASE_URL"]
deployment = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]

token_provider = get_bearer_token_provider(
    AzureCliCredential(),
    "https://ai.azure.com/.default",
)

client = OpenAI(
    base_url=endpoint,
    api_key=token_provider,
)

response = client.responses.create(
    model=deployment,
    input=(
        "Extract the product description and quantity from: "
        "'I need 10 safety helmets.' Return only JSON."
    ),
    max_output_tokens=500,
    store=False,
)

print(response.output_text)