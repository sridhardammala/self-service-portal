# First get all project IDs
PROJECTS=$(gcloud projects list --format="value(projectId)")

# Then apply to each project
for PROJECT in $PROJECTS; do
  echo "Granting access to $PROJECT"
  gcloud projects add-iam-policy-binding $PROJECT \
    --member="serviceAccount:admin-operations@mt-2dportal.iam.gserviceaccount.com" \
    --role="roles/storage.admin" \
    --condition=None
done