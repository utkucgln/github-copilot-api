# GitHub Copilot as API - Dockerfile
# For deployment to Azure Container Apps / Azure Functions

FROM mcr.microsoft.com/azure-functions/python:4-python3.11

# Install Node.js and GitHub Copilot CLI
RUN apt-get update && apt-get install -y curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @github/copilot && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    FUNCTIONS_WORKER_RUNTIME=python \
    COPILOT_PATH=copilot

COPY requirements.txt /
RUN pip install -r /requirements.txt

COPY . /home/site/wwwroot

WORKDIR /home/site/wwwroot

# GH_TOKEN must be set as environment variable when running the container
# Create a GitHub PAT with 'Copilot Requests' permission from: 
# https://github.com/settings/personal-access-tokens/new

EXPOSE 80
