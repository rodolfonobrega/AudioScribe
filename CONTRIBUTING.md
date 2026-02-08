# Contributing to AudioScribe

Thank you for your interest in contributing to AudioScribe! This document provides guidelines and instructions for contributing.

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- A code editor (VS Code, PyCharm, etc.)

### Setting Up Development Environment

```bash
# Fork and clone the repository
git clone https://github.com/rodolfonobrega/audioscribe.git
cd audioscribe

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install in editable mode
pip install -e .
```

## 📋 Development Guidelines

### Code Style

We use **black** for code formatting:

```bash
# Format code
black .

# Check formatting
black --check .
```

### Type Hints

All code should include type hints:

```python
from typing import Optional, List

def process_text(text: str, options: Optional[dict] = None) -> List[str]:
    # Your code here
    pass
```

### Testing

Write tests for new features:

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=core --cov=config
```

### Documentation

Update documentation for new features:
- Add docstrings to all functions and classes
- Update README.md if needed
- Add examples to example_usage.py

## 🔄 Workflow

1. **Create a branch** for your feature or bugfix
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** and commit them
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

3. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create a Pull Request** on GitHub

## 📝 Commit Message Format

We follow conventional commits:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test changes
- `refactor:` - Code refactoring
- `style:` - Code style changes
- `chore:` - Maintenance tasks

Example:
```bash
git commit -m "feat: add support for Azure transcriber"
```

## 🐛 Reporting Bugs

When reporting bugs, please include:

- Python version
- Operating system
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error messages (if any)

## 💡 Feature Requests

For feature requests:

- Explain the use case
- Provide examples of how it would be used
- Consider if it fits the project's scope

---

Thank you for contributing! 🎉
