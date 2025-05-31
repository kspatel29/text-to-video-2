#!/bin/bash

# --- Configuration ---
# These should match the resources you've already created manually.
RESOURCE_GROUP_NAME="text-to-video-rg"
LOCATION="East US"  # Change this to your preferred Azure region
ACR_NAME="texttovideoregistry"
WEB_APP_NAME="text-to-video-app"
APP_SERVICE_PLAN_NAME="text-to-video-plan"
DOCKER_IMAGE_NAME="text-to-video-flask" # The name of the image in ACR

# App Service Plan Configuration
# P2v2: 2 vCPUs, 7GB RAM (closest to requested 8GB)
# Other options: P1v2 (1 vCPU, 3.5GB), P3v2 (4 vCPU, 14GB)
APP_SERVICE_PLAN_SKU="P2v2"

# --- Generated names ---
# Generate a new tag for the image (e.g., based on timestamp)
NEW_DOCKER_IMAGE_TAG="v$(date +%Y%m%d%H%M%S)"
ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"
FULL_IMAGE_NAME_WITH_TAG="${ACR_LOGIN_SERVER}/${DOCKER_IMAGE_NAME}:${NEW_DOCKER_IMAGE_TAG}"

# --- Script ---
echo "Starting deployment/update process for Flask Video Generation App..."

# 0. Ensure you are logged into Azure
echo "Verifying Azure login status..."
az account show > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "Error: You are not logged into Azure. Please run 'az login' and try again."
  exit 1
fi
echo "Azure login verified."

# 1. Create resource group if it doesn't exist
echo "Ensuring resource group $RESOURCE_GROUP_NAME exists in $LOCATION..."
az group create --name "$RESOURCE_GROUP_NAME" \
               --location "$LOCATION" \
               --output none 2>/dev/null || echo "Resource group already exists or creation failed, continuing..."

# Check if resource group exists
az group show --name "$RESOURCE_GROUP_NAME" --output none
if [ $? -ne 0 ]; then
  echo "Error: Resource group $RESOURCE_GROUP_NAME does not exist and could not be created."
  echo "Please create it manually with: az group create --name $RESOURCE_GROUP_NAME --location '$LOCATION'"
  exit 1
fi
echo "Resource group $RESOURCE_GROUP_NAME is ready."

# 2. Create Azure Container Registry if it doesn't exist
echo "Ensuring Azure Container Registry $ACR_NAME exists..."
az acr create --name "$ACR_NAME" \
             --resource-group "$RESOURCE_GROUP_NAME" \
             --location "$LOCATION" \
             --sku Standard \
             --admin-enabled false \
             --output none 2>/dev/null || echo "ACR already exists or creation failed, continuing..."

# Check if ACR exists
az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP_NAME" --output none
if [ $? -ne 0 ]; then
  echo "Error: Azure Container Registry $ACR_NAME does not exist and could not be created."
  echo "Please create it manually with: az acr create --name $ACR_NAME --resource-group $RESOURCE_GROUP_NAME --sku Standard"
  exit 1
fi
echo "Azure Container Registry $ACR_NAME is ready."

# 3. Create or update App Service Plan with specified resources
echo "Configuring App Service Plan $APP_SERVICE_PLAN_NAME with $APP_SERVICE_PLAN_SKU (2 vCPUs, 7GB RAM)..."
az appservice plan create --name "$APP_SERVICE_PLAN_NAME" \
                         --resource-group "$RESOURCE_GROUP_NAME" \
                         --sku "$APP_SERVICE_PLAN_SKU" \
                         --is-linux \
                         --output none 2>/dev/null || \
az appservice plan update --name "$APP_SERVICE_PLAN_NAME" \
                         --resource-group "$RESOURCE_GROUP_NAME" \
                         --sku "$APP_SERVICE_PLAN_SKU" \
                         --output none

if [ $? -ne 0 ]; then
  echo "Error: Failed to create/update App Service Plan. Please check if the plan exists and you have permissions."
  exit 1
fi
echo "App Service Plan configured successfully with 2 vCPUs and 7GB RAM."

# 4. Ensure Web App exists and is associated with the correct plan
echo "Ensuring Web App $WEB_APP_NAME exists and is configured..."
az webapp create --name "$WEB_APP_NAME" \
                --resource-group "$RESOURCE_GROUP_NAME" \
                --plan "$APP_SERVICE_PLAN_NAME" \
                --deployment-container-image-name "nginx" \
                --output none 2>/dev/null || echo "Web App already exists, continuing..."

# 5. Build and Push Docker Image to ACR using 'az acr build'
# This command builds the Dockerfile in the current directory (.) 
# and pushes the image to your ACR with the new tag.
echo "Building and pushing Docker image to ACR: $ACR_NAME"
echo "Image: $DOCKER_IMAGE_NAME:$NEW_DOCKER_IMAGE_TAG"

az acr build --resource-group "$RESOURCE_GROUP_NAME" \
             --registry "$ACR_NAME" \
             --image "$DOCKER_IMAGE_NAME:$NEW_DOCKER_IMAGE_TAG" \
             .

if [ $? -ne 0 ]; then
  echo "Error: Docker image build and/or push failed."
  exit 1
fi
echo "Docker image built and pushed successfully: $FULL_IMAGE_NAME_WITH_TAG"

# 6. Ensure Web App is configured to use Managed Identity for ACR pull
echo "Configuring Web App $WEB_APP_NAME to use Managed Identity for ACR pull..."
az webapp update --name "$WEB_APP_NAME" \
                 --resource-group "$RESOURCE_GROUP_NAME" \
                 --set siteConfig.acrUseManagedIdentityCreds=true --output none

if [ $? -ne 0 ]; then
  echo "Warning: Failed to explicitly set acrUseManagedIdentityCreds. If managed identity is already correctly configured, deployment might still succeed."
fi

# 7. Configure Web App for HTTPS and proper port mapping
echo "Configuring Web App settings for Flask application..."
az webapp config appsettings set --name "$WEB_APP_NAME" \
                                --resource-group "$RESOURCE_GROUP_NAME" \
                                --settings WEBSITES_PORT=5000 \
                                           FLASK_ENV=production \
                                           PYTHONUNBUFFERED=1 \
                                --output none

if [ $? -ne 0 ]; then
  echo "Warning: Failed to set application settings. Continuing with deployment."
fi

# 8. Update Web App to use the new image
echo "Updating Web App $WEB_APP_NAME to use new image: $FULL_IMAGE_NAME_WITH_TAG..."
az webapp config container set --name "$WEB_APP_NAME" \
                             --resource-group "$RESOURCE_GROUP_NAME" \
                             --container-image-name "$FULL_IMAGE_NAME_WITH_TAG" \
                             --container-registry-url "https://$ACR_LOGIN_SERVER" \
                             --output none

if [ $? -ne 0 ]; then
  echo "Error: Web App container configuration update failed. This might be due to a delay in Managed Identity permission propagation or an incorrect setup."
  echo "Please verify that the Web App's Managed Identity has the 'AcrPull' role on the ACR '${ACR_NAME}'."
  exit 1
fi

# 9. Enable continuous deployment webhook (optional, but good for future updates from ACR)
echo "Enabling CI/CD webhook for Web App $WEB_APP_NAME (best practice)..."
az webapp deployment container config --enable-cd true \
                                   --name "$WEB_APP_NAME" \
                                   --resource-group "$RESOURCE_GROUP_NAME" \
                                   --output none
if [ $? -ne 0 ]; then
  echo "Warning: Failed to enable CI/CD webhook. This is optional for this script's flow."
fi

# 10. Configure health check endpoint (optional but recommended)
echo "Setting up health check for the Flask application..."
az webapp config set --name "$WEB_APP_NAME" \
                    --resource-group "$RESOURCE_GROUP_NAME" \
                    --generic-configurations '{"healthCheckPath": "/health"}' \
                    --output none
if [ $? -ne 0 ]; then
  echo "Warning: Failed to set health check path. This is optional."
fi

echo "--- Deployment/Update Complete ---"
echo "Web App $WEB_APP_NAME is being updated with image: $FULL_IMAGE_NAME_WITH_TAG"
echo "It might take a few moments for the changes to reflect."
echo "You can monitor the deployment logs in the Azure portal or via Azure CLI."
echo "Access your application at: https://$WEB_APP_NAME.azurewebsites.net"
echo ""
echo "API Endpoints available:"
echo "  POST https://$WEB_APP_NAME.azurewebsites.net/generate-video"
echo "  GET  https://$WEB_APP_NAME.azurewebsites.net/video-status/<request_id>"
echo "  GET  https://$WEB_APP_NAME.azurewebsites.net/download-video/<request_id>"
echo ""
echo "Note: The application uses HTTPS with self-signed certificates internally."
echo "Azure App Service will handle SSL termination, so external access will use Azure's certificates."

echo "Deployment script finished."