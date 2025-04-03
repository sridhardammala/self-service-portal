from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from google.cloud import resourcemanager_v3, storage
from google.api_core.exceptions import Conflict, BadRequest
from google.auth import default
import secrets
from typing import Dict, Optional
import os

app = FastAPI()

# Session management
active_sessions: Dict[str, str] = {}  # session_token: username

# Mount static files for CSS
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Path to your Service Account key file
# SERVICE_ACCOUNT_KEY_PATH = "/home/sridhar_mindtrace_ai/sri/data/github-sa.json"

# # Authenticate using the Service Account key
# def get_credentials():
#     return service_account.Credentials.from_service_account_file(
#         SERVICE_ACCOUNT_KEY_PATH,
#         scopes=["https://www.googleapis.com/auth/cloud-platform"],
#     )

# Fetch GCP projects
def get_gcp_projects():
    # credentials = get_credentials()
    credentials, _ = default()  # Use ADC for credentials, ignore the default project
    # print(f"Using credentials for project: {project}")
    client = resourcemanager_v3.ProjectsClient(credentials=credentials)
    projects = client.search_projects()
    return [project.project_id for project in projects]

# Mock user authentication (replace with real authentication logic)
def authenticate_user(username: str, password: str):
    if username == "user" and password == "password":
        return True
    return False

# Authentication dependency
async def get_current_user(request: Request):
    session_token = request.cookies.get("session_token")
    if not session_token or session_token not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": "/login"}
        )
    return active_sessions[session_token]

# Update the login endpoint to create session
@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if authenticate_user(username, password):
        session_token = secrets.token_hex(32)
        active_sessions[session_token] = username
        
        response = RedirectResponse(url="/home", status_code=303)
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            # secure=True,  # Enable in production with HTTPS
            secure=False,  # Disable for testing HTTP
            samesite="lax"
        )
        return response
    raise HTTPException(status_code=401, detail="Invalid credentials")

# Add logout endpoint
@app.get("/logout")
async def logout(request: Request):
    session_token = request.cookies.get("session_token")
    if session_token in active_sessions:
        del active_sessions[session_token]
    response = RedirectResponse(url="/login")
    response.delete_cookie("session_token")
    return response

@app.post("/logout")  # Changed from @app.get to @app.post
async def logout(request: Request):
    session_token = request.cookies.get("session_token")
    if session_token in active_sessions:
        del active_sessions[session_token]
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("session_token")
    return response

# Add this new route for the home page (now protected)
@app.get("/home", response_class=HTMLResponse)
async def home(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("home.html", {"request": request, "user": user})

# Example Health Check Endpoint (no auth needed)
@app.get("/healthz")
async def health_check():
    return JSONResponse(status_code=200, content={"status": "healthy"})

# Update the root endpoint
@app.get("/")
async def root():
    return RedirectResponse(url="/login")

# GCP Projects Page (now protected)
@app.get("/projects", response_class=HTMLResponse)
async def projects(request: Request, user: str = Depends(get_current_user)):
    projects = get_gcp_projects()
    print(f'GCP Proejcts are: {projects}')
    return templates.TemplateResponse(
        "projects.html", 
        {"request": request, "projects": projects, "user": user}
    )

# Grant Access to GCP Project (now protected)
@app.post("/grant-access")
async def grant_access(request: Request, user: str = Depends(get_current_user)):
    form_data = await request.form()
    form_dict = dict(form_data)
    
    print(f"Received form data: {form_dict}")
    
    project = form_dict.get("project")
    target_user = form_dict.get("user")
    
    if not project or not target_user:
        return {"error": "Missing required fields"}
    
    credentials, _ = default()
    print(f"Using credentials for project: {project}")
    
    client = resourcemanager_v3.ProjectsClient(credentials=credentials)
    
    try:
        policy = client.get_iam_policy(request={"resource": f"projects/{project}"})
        print(f"Current IAM policy retrieved successfully.")
    except Exception as e:
        print(f"Failed to retrieve IAM policy: {e}")
        return {"error": "Failed to retrieve IAM policy"}
    
    policy.bindings.add(role="roles/viewer", members=[f"user:{target_user}"])
    print(f"Added user {target_user} with 'roles/viewer' to the IAM policy.")
    
    try:
        client.set_iam_policy(request={"resource": f"projects/{project}", "policy": policy})
        print(f"Successfully set IAM policy for project {project}.")
    except Exception as e:
        print(f"Failed to set IAM policy: {e}")
        return {"error": "Failed to set IAM policy"}
    
    return RedirectResponse(url="/projects", status_code=303)

def get_gcp_buckets(project_id):
    credentials, _ = default()
    storage_client = storage.Client(credentials=credentials, project=project_id)
    buckets = list(storage_client.list_buckets())
    return [bucket.name for bucket in buckets]

# Bucket Access Page (now protected)
@app.get("/bucket-access", response_class=HTMLResponse)
async def bucket_access(request: Request, user: str = Depends(get_current_user)):
    projects = get_gcp_projects()
    return templates.TemplateResponse(
        "bucket-access.html", 
        {"request": request, "projects": projects, "user": user, "buckets": []}
    )

# New endpoint to fetch buckets for a project
@app.get("/get-buckets/{project_id}")
async def get_buckets(project_id: str, user: str = Depends(get_current_user)):
    try:
        buckets = get_gcp_buckets(project_id)
        return {"buckets": buckets}
    except Exception as e:
        return {"error": str(e)}

# Grant Storage Admin Access to a GCP Bucket (now protected)
# Grant Storage Admin Access to a GCP Bucket (now protected)
@app.post("/request-bucket-access")
async def grant_storage_admin_access(request: Request, user: str = Depends(get_current_user)):
    form_data = await request.form()
    form_dict = dict(form_data)
    
    print(f"Received form data: {form_dict}")
    
    project = form_dict.get("project")
    bucket_name = form_dict.get("bucket_name")
    target_user = form_dict.get("user")
    
    if not project or not bucket_name or not target_user:
        return {"error": "Missing required fields (project, bucket name, user)"}
    
    credentials, _ = default()
    
    storage_client = storage.Client(credentials=credentials, project=project)
    
    try:
        bucket = storage_client.get_bucket(bucket_name)
        policy = bucket.get_iam_policy()
        print(f"Retrieved IAM policy for bucket: {bucket_name}")
    except Exception as e:
        print(f"Failed to retrieve IAM policy for bucket {bucket_name}: {e}")
        return {"error": f"Failed to retrieve IAM policy for bucket {bucket_name}"}
    
    policy.bindings.append({
        "role": "roles/storage.admin",
        "members": [f"user:{target_user}"]
    })
    print(f"Added user {target_user} with 'roles/storage.admin' to the IAM policy.")
    
    try:
        bucket.set_iam_policy(policy)
        print(f"Successfully set IAM policy for bucket {bucket_name}.")
        # Add success parameter here when everything works
        return RedirectResponse(url="/bucket-access?success=true", status_code=303)
    except Exception as e:
        print(f"Failed to set IAM policy for bucket {bucket_name}: {e}")
        return {"error": f"Failed to set IAM policy for bucket {bucket_name}"}
    
    # Remove this line as it's unreachable after the try/except blocks
    # return RedirectResponse(url="/bucket-access", status_code=303)
# Bucket Access Page (now protected)
# @app.get("/bucket-access", response_class=HTMLResponse)
# async def bucket_access(request: Request, user: str = Depends(get_current_user)):
#     projects = get_gcp_projects()
#     print(f'GCP Proejcts are: {projects}')
#     return templates.TemplateResponse(
#         "bucket-access.html", 
#         {"request": request, "projects": projects, "user": user}    
#     )

# # Grant Storage Admin Access to a GCP Bucket (now protected)
# @app.post("/request-bucket-access")
# async def grant_storage_admin_access(request: Request, user: str = Depends(get_current_user)):
#     form_data = await request.form()
#     form_dict = dict(form_data)
    
#     print(f"Received form data: {form_dict}")
    
#     project = form_dict.get("project")
#     bucket_name = form_dict.get("bucket_name")
#     target_user = form_dict.get("user")
    
#     if not project or not bucket_name or not target_user:
#         return {"error": "Missing required fields (project, bucket name, user)"}
    
#     credentials, _ = default()
#     print(f"Using credentials for project: {project}")
    
#     storage_client = storage.Client(credentials=credentials, project=project)
    
#     try:
#         bucket = storage_client.get_bucket(bucket_name)
#         policy = bucket.get_iam_policy()
#         print(f"Retrieved IAM policy for bucket: {bucket_name}")
#     except Exception as e:
#         print(f"Failed to retrieve IAM policy for bucket {bucket_name}: {e}")
#         return {"error": f"Failed to retrieve IAM policy for bucket {bucket_name}"}
    
#     policy.bindings.append({
#         "role": "roles/storage.admin",
#         "members": [f"user:{target_user}"]
#     })
#     print(f"Added user {target_user} with 'roles/storage.admin' to the IAM policy.")
    
#     try:
#         bucket.set_iam_policy(policy)
#         print(f"Successfully set IAM policy for bucket {bucket_name}.")
#     except Exception as e:
#         print(f"Failed to set IAM policy for bucket {bucket_name}: {e}")
#         return {"error": f"Failed to set IAM policy for bucket {bucket_name}"}
    
#     return RedirectResponse(url="/bucket-access", status_code=303)

# Create Bucket Page (now protected)
@app.get("/create-bucket", response_class=HTMLResponse)
async def create_bucket_page(request: Request, user: str = Depends(get_current_user)):
    # return templates.TemplateResponse(
    #     "create-bucket.html", 
    #     {"request": request, "user": user}
    # )
    projects = get_gcp_projects()
    return templates.TemplateResponse(
        "create-bucket.html", 
        {"request": request, "projects": projects, "user": user, "buckets": []}
    )

# Create Bucket endpoint (now protected)
@app.post("/create-bucket")
async def create_bucket(request: Request, user: str = Depends(get_current_user)):
    form_data = await request.form()
    form_dict = dict(form_data)

    print("\nReceived bucket creation request:")
    for key, value in form_dict.items():
        print(f"  {key}: {value}")

    new_bucket_name = form_dict.get("new_bucket_name")
    project = form_dict.get("project")
    region = form_dict.get("region")
    target_user = form_dict.get("user")

    if not all([new_bucket_name, project, region, target_user]):
        print("Error: Missing required fields.")
        return {"error": "All fields (bucket name, project, region, user) are required"}

    credentials, _ = default()
    print(f"Authenticated with project: {project}")

    storage_client = storage.Client(credentials=credentials, project=project)
    bucket = storage_client.bucket(new_bucket_name)
    print(f"Bucket object created: {bucket}")

    bucket.location = region
    created_bucket = storage_client.create_bucket(bucket)
    print(f"\nSuccessfully created bucket: {created_bucket.name}")

    policy = created_bucket.get_iam_policy()
    policy.bindings.append({
        "role": "roles/storage.admin",
        "members": [f"user:{target_user}"]
    })
    created_bucket.set_iam_policy(policy)
    print("IAM policy updated successfully.")

    return RedirectResponse(
        url=f"/create-bucket?success=Bucket+{new_bucket_name}+created",
        status_code=303
    )

# Login Page (no auth needed)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Run the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)