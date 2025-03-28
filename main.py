from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from google.cloud import resourcemanager_v3
from google.oauth2 import service_account
import os
from google.cloud import storage
from google.api_core.exceptions import Conflict, BadRequest
from google.auth import default

app = FastAPI()

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



# Update the login endpoint to redirect to home.html
@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if authenticate_user(username, password):
        return RedirectResponse(url="/home", status_code=303)  # Changed from "/projects" to "/home"
    raise HTTPException(status_code=401, detail="Invalid credentials")

# Add this new route for the home page
@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

# Example Health Check Endpoint
@app.get("/healthz")
async def health_check():
    # Here you can add more logic to check actual service health, e.g., database connectivity, etc.
    return JSONResponse(status_code=200, content={"status": "healthy"})

# Update the root endpoint to redirect to home if authenticated (optional)
@app.get("/")
async def root(request: Request):
    # You could add authentication check here if you want
    # to automatically redirect logged-in users to home
    return RedirectResponse(url="/login")

# GCP Projects Page
@app.get("/projects", response_class=HTMLResponse)
async def projects(request: Request):
    projects = get_gcp_projects()
    return templates.TemplateResponse("projects.html", {"request": request, "projects": projects})
# Grant Access to GCP Project
@app.post("/grant-access")
async def grant_access(request: Request):
    form_data = await request.form()
    form_dict = dict(form_data)
    
    # Print received form data for debugging
    print(f"Received form data: {form_dict}")
    
    project = form_dict.get("project")
    user = form_dict.get("user")
    
    # Print project and user information
    print(f"Granting access to project: {project} for user: {user}")
    
    if not project or not user:
        return {"error": "Missing required fields"}
    
    # Initialize credentials using custom project
    credentials, _ = default()  # Use ADC for credentials, ignore the default project
    print(f"Using credentials for project: {project}")
    
    # Initialize the GCP Resource Manager Client
    client = resourcemanager_v3.ProjectsClient(credentials=credentials)
    
    # Retrieve the current IAM policy for the project
    try:
        policy = client.get_iam_policy(request={"resource": f"projects/{project}"})
        print(f"Current IAM policy retrieved successfully.")
    except Exception as e:
        print(f"Failed to retrieve IAM policy: {e}")
        return {"error": "Failed to retrieve IAM policy"}
    
    # Add the user to the IAM policy (with Viewer role)
    policy.bindings.add(role="roles/viewer", members=[f"user:{user}"])
    print(f"Added user {user} with 'roles/viewer' to the IAM policy.")
    
    # Set the updated IAM policy
    try:
        client.set_iam_policy(request={"resource": f"projects/{project}", "policy": policy})
        print(f"Successfully set IAM policy for project {project}.")
    except Exception as e:
        print(f"Failed to set IAM policy: {e}")
        return {"error": "Failed to set IAM policy"}
    
    return RedirectResponse(url="/projects", status_code=303)
# Bucket Access Page
@app.get("/bucket-access", response_class=HTMLResponse)
async def bucket_access(request: Request):
    return templates.TemplateResponse("bucket-access.html", {"request": request})

# Grant Storage Admin Access to a GCP Bucket
@app.post("/request-bucket-access")
async def grant_storage_admin_access(request: Request):
    form_data = await request.form()
    form_dict = dict(form_data)
    
    # Print received form data for debugging
    print(f"Received form data: {form_dict}")
    
    project = form_dict.get("project")
    bucket_name = form_dict.get("bucket_name")
    user = form_dict.get("user")
    
    # Print project, bucket, and user information
    print(f"Granting 'Storage Admin' access to bucket: {bucket_name} in project: {project} for user: {user}")
    
    if not project or not bucket_name or not user:
        return {"error": "Missing required fields (project, bucket name, user)"}
    
    # Initialize credentials using custom project
    credentials, _ = default()  # Use ADC for credentials, ignore the default project
    print(f"Using credentials for project: {project}")
    
    # Initialize the GCP Storage Client
    storage_client = storage.Client(credentials=credentials, project=project)
    
    try:
        # Retrieve the IAM policy for the specified bucket
        bucket = storage_client.get_bucket(bucket_name)
        policy = bucket.get_iam_policy()
        print(f"Retrieved IAM policy for bucket: {bucket_name}")
    except Exception as e:
        print(f"Failed to retrieve IAM policy for bucket {bucket_name}: {e}")
        return {"error": f"Failed to retrieve IAM policy for bucket {bucket_name}"}
    
    # Add the user to the IAM policy with "Storage Admin" role
    policy.bindings.append({
        "role": "roles/storage.admin",  # "Storage Admin" role
        "members": [f"user:{user}"]
    })
    print(f"Added user {user} with 'roles/storage.admin' to the IAM policy for bucket {bucket_name}.")
    
    try:
        # Set the updated IAM policy for the bucket
        bucket.set_iam_policy(policy)
        print(f"Successfully set IAM policy for bucket {bucket_name}.")
    except Exception as e:
        print(f"Failed to set IAM policy for bucket {bucket_name}: {e}")
        return {"error": f"Failed to set IAM policy for bucket {bucket_name}"}
    
    return RedirectResponse(url="/bucket-access", status_code=303)

# Create Bucket Page
@app.get("/create-bucket", response_class=HTMLResponse)
async def create_bucket(request: Request):
    return templates.TemplateResponse("create-bucket.html", {"request": request})

@app.post("/create-bucket")
async def create_bucket(request: Request):
    # Get all form data as a dictionary
    form_data = await request.form()
    form_dict = dict(form_data)

    # Print all received form data
    print("\nReceived bucket creation request:")
    for key, value in form_dict.items():
        print(f"  {key}: {value}")

    # Access and validate all required fields
    new_bucket_name = form_dict.get("new_bucket_name")
    project = form_dict.get("project")
    region = form_dict.get("region")
    user = form_dict.get("user")

    if not all([new_bucket_name, project, region, user]):
        print("Error: Missing required fields.")
        return {"error": "All fields (bucket name, project, region, user) are required"}

    # Initialize storage client
    # credentials, project = default()
    credentials, _ = default()  # Ignore the default project

    storage_client = storage.Client(credentials=credentials, project=project)
    print(f"Authenticated with project: {project}")

    # Create bucket object
    bucket = storage_client.bucket(new_bucket_name)
    print(f"Bucket object created: {bucket}")

    # Set bucket location
    bucket.location = region  # No need to convert to uppercase

    # Create the bucket in GCP
    created_bucket = storage_client.create_bucket(bucket)
    print(f"\nSuccessfully created bucket: {created_bucket.name}")

    # Set bucket IAM policy for the user
    policy = created_bucket.get_iam_policy()
    policy.bindings.append({
        "role": "roles/storage.admin",
        "members": [f"user:{user}"]
    })
    created_bucket.set_iam_policy(policy)
    print("IAM policy updated successfully.")

    return RedirectResponse(
        url=f"/create-bucket?success=Bucket+{new_bucket_name}+created",
        status_code=303
    )

# Root redirect to login
@app.get("/")
async def root():
    return RedirectResponse(url="/login")

# Login Page
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Run the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)