# DefectDojo (chapter 8)

We run DefectDojo from its **official repository**, unchanged, plus one small
override file of our own that keeps it on localhost.

```bash
cd ~
git clone https://github.com/DefectDojo/django-DefectDojo.git
cd django-DefectDojo
git tag --sort=-v:refname | head -5          # pick the newest release tag
git checkout <that-tag>
cp ~/devsecops-pipeline/platform/defectdojo/docker-compose.override.yml .
docker compose config --services             # confirm there is an "nginx" service
docker compose up -d                         # first start takes several minutes
docker compose logs initializer | grep "Admin password:"
```

Open `http://localhost:8080` through the SSH tunnel and log in as `admin`.

**API key for the pipeline:** user menu (top right) → **API v2 Key** → copy.
Store it in GitHub, never in a file:

```bash
gh secret set DOJO_API_KEY --repo OWNER/REPO      # paste at the prompt
gh variable set DOJO_URL --repo OWNER/REPO --body "http://127.0.0.1:8080"
gh variable set DOJO_ENABLED --repo OWNER/REPO --body "true"
```

The admin key is fine for a private tutorial. For real use, create a separate
user with access to this product only and use its key.

Official docs: https://docs.defectdojo.com/
