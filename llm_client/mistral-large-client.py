"""Run this model in Python

> pip install mistralai>=1.0.0
"""
import os
from mistralai import Mistral, UserMessage, SystemMessage

# To authenticate with the model you will need to generate a personal access token (PAT) in your GitHub settings. 
# Create your PAT token by following instructions here: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
client = Mistral(
    api_key=os.environ["GITHUB_TOKEN"],
    server_url="https://models.github.ai/inference"
)

response = client.chat(
    model="Mistral-large-2407",
    messages=[
        SystemMessage(""),
        UserMessage("What is the capital of France?"),
    ],
    temperature=0.8,
    max_tokens=2048,
    top_p=0.1
)

print(response.choices[0].message.content)
