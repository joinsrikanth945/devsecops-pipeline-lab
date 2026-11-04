# Chapter 4 demo: a planted fake secret

Goal: show that deleting a secret in a later commit does not remove it from
Git history, and that Gitleaks still finds it.

Do this on a throw-away branch, with a **fake** value you make up on the spot.
Never use a real key, not even an expired one.

```bash
git switch -c demo-leak
# build a fake GitHub-token-shaped string: "ghp_" + 36 random letters/digits
fake="ghp_$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 36)"
echo "GITHUB_TOKEN=$fake" > demo/settings.env
git add demo/settings.env && git commit -m "demo: add settings"
git rm demo/settings.env && git commit -m "demo: remove settings"
git push -u origin demo-leak
```

Then run the pipeline on that branch (Actions -> pipeline -> Run workflow ->
branch demo-leak) and open `reports/gitleaks.json` in the artifact: the leak is
reported with the commit that added it, and the value is redacted.

Clean-up afterwards:

```bash
git switch main
git push origin --delete demo-leak
git branch -D demo-leak
```
