"""
GitHub Copilot as API - Azure Functions App
Exposes GitHub Copilot CLI as REST API endpoints.
"""

import azure.functions as func
import logging
import json

from services.copilot_service import CopilotService
from services.auth_service import AuthService

# Initialize the Function App with Anonymous auth (our AuthService handles API key validation)
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Initialize services
copilot_service = CopilotService()
auth_service = AuthService()


@app.route(route="chat", methods=["POST"])
async def chat(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/chat
    
    Chat endpoint using GitHub Copilot CLI (new version).
    
    Request Body:
    {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "How do I list files in a directory?"}
        ],
        "model": "claude-sonnet-4"  // optional: claude-sonnet-4, gpt-5, etc.
    }
    
    Response:
    {
        "id": "copilot-xxx",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "You can use ls -la to list files..."
                },
                "finish_reason": "stop"
            }
        ]
    }
    """
    logging.info("Chat endpoint called")
    
    try:
        # Validate authentication
        auth_header = req.headers.get("Authorization")
        if not auth_service.validate_token(auth_header):
            return func.HttpResponse(
                json.dumps({"error": "Unauthorized"}),
                status_code=401,
                mimetype="application/json"
            )
        
        # Parse request body
        req_body = req.get_json()
        messages = req_body.get("messages", [])
        model = req_body.get("model")
        
        if not messages:
            return func.HttpResponse(
                json.dumps({"error": "Messages are required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Call copilot service
        response = await copilot_service.chat(
            messages=messages,
            model=model
        )
        
        return func.HttpResponse(
            json.dumps(response),
            status_code=200,
            mimetype="application/json"
        )
        
    except json.JSONDecodeError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Error in chat endpoint: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error", "details": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="stream", methods=["POST"])
async def stream(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/stream
    
    Streaming chat endpoint using Server-Sent Events (SSE).
    Note: Simulated streaming since CLI doesn't support native streaming.
    
    Request Body:
    {
        "messages": [
            {"role": "user", "content": "Explain git rebase"}
        ],
        "model": "claude-sonnet-4"  // optional
    }
    
    Response: Server-Sent Events stream
    """
    logging.info("Stream endpoint called")
    
    try:
        # Validate authentication
        auth_header = req.headers.get("Authorization")
        if not auth_service.validate_token(auth_header):
            return func.HttpResponse(
                json.dumps({"error": "Unauthorized"}),
                status_code=401,
                mimetype="application/json"
            )
        
        # Parse request body
        req_body = req.get_json()
        messages = req_body.get("messages", [])
        model = req_body.get("model")
        
        if not messages:
            return func.HttpResponse(
                json.dumps({"error": "Messages are required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Get streaming response (returns tuple of stream_content and files)
        stream_content, files = await copilot_service.stream_chat(
            messages=messages,
            model=model
        )
        
        return func.HttpResponse(
            stream_content,
            status_code=200,
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
        
    except json.JSONDecodeError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Error in stream endpoint: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error", "details": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="health", methods=["GET"])
async def health(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/health
    
    Health check endpoint - also checks Copilot CLI availability.
    """
    copilot_status = await copilot_service.check_copilot_available()
    
    status = "healthy" if copilot_status.get("available") else "degraded"
    
    return func.HttpResponse(
        json.dumps({
            "status": status,
            "service": "github-copilot-api",
            "version": "2.0.0",
            "copilot": copilot_status
        }),
        status_code=200 if status == "healthy" else 503,
        mimetype="application/json"
    )


@app.route(route="models", methods=["GET"])
async def models(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/models
    
    List available models from Copilot CLI.
    """
    logging.info("Models endpoint called")
    
    try:
        auth_header = req.headers.get("Authorization")
        if not auth_service.validate_token(auth_header):
            return func.HttpResponse(
                json.dumps({"error": "Unauthorized"}),
                status_code=401,
                mimetype="application/json"
            )
        
        available_models = copilot_service.get_available_models()
        
        return func.HttpResponse(
            json.dumps({"models": available_models}),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error in models endpoint: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
