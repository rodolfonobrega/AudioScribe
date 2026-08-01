# Automated Release Guide for AudioScribe

AudioScribe uses **GitHub Actions CI/CD** to automatically compile Python binaries (`PyInstaller`) and package Electron Desktop installers (`electron-builder`) whenever a new version tag is pushed to GitHub.

---

## 🚀 How to Publish a New Release (.exe, .dmg, .AppImage)

Follow these simple steps to create a new release on GitHub:

### 1. Commit and Push all changes to main
```bash
git add .
git commit -m "feat: release version 1.0.0"
git push origin main
```

### 2. Create and Push a Version Tag
To trigger the automated release pipeline, create a git tag starting with `v` (e.g. `v1.0.0`):

```bash
# Create a tag locally
git tag v1.0.0

# Push the tag to GitHub
git push origin v1.0.0
```

### 3. Automated CI/CD Execution
Once the tag is pushed:
1. GitHub Actions automatically starts the workflow defined in `.github/workflows/release.yml`.
2. It spins up 3 parallel virtual machines:
   - **Windows Runner (`windows-latest`)**: Builds `AudioScribe-Setup-1.0.0.exe` (NSIS installer).
   - **macOS Runner (`macos-latest`)**: Builds `AudioScribe-1.0.0.dmg` (macOS package).
   - **Linux Runner (`ubuntu-latest`)**: Builds `AudioScribe-1.0.0.AppImage` (Linux portable binary).
3. The built installer files are automatically uploaded as downloadable assets to the GitHub Releases tab!

---

## 🔍 Manual Trigger Option
You can also trigger a release build manually from GitHub:
1. Go to your repository on GitHub.
2. Click on **Actions** > **Build and Publish Releases**.
3. Click **Run workflow** > Select `main` branch > Click **Run workflow**.
