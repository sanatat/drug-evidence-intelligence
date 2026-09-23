# Publish this project to GitHub

The repository is prepared so that source PDFs, uploaded documents, archives, and local SQLite databases are ignored by Git.

## 1. Create an empty GitHub repository

Suggested repository name:

```text
drug-evidence-intelligence
```

Do not initialize it with a README or licence if you are pushing this prepared folder.

## 2. Initialize Git locally

From the project folder:

```bash
git init
git branch -M main
git add .
git status
```

Before committing, inspect `git status` carefully. There should be **no real PDFs, ZIP/RAR archives, or `.db` files** staged.

Then:

```bash
git commit -m "Initial public research release"
```

## 3. Connect the GitHub repository

Replace the URL below with your repository URL:

```bash
git remote add origin https://github.com/YOUR_USERNAME/drug-evidence-intelligence.git
git push -u origin main
```

## 4. Recommended GitHub About text

**Description**

> Local research pipeline for structured extraction and comparison of pharmacopoeial, regulatory, HTA, and clinical-study evidence from drug PDFs.

**Topics**

```text
pharmacopoeia
health-technology-assessment
regulatory-science
clinical-research
meta-analysis
natural-language-processing
generative-ai
fastapi
sqlite
pharmaceutical-sciences
```

## 5. Before making the repository public

- run `pytest`;
- run `git status --ignored` and check that private data are ignored;
- replace `<your-repository-url>` in the README after the GitHub repository exists;
- optionally add your name/ORCID to `CITATION.cff` after you decide how you want authorship displayed.
