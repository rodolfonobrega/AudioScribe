"""
Setup configuration for AudioScribe
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    requirements = [
        line.strip()
        for line in requirements_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="audioscribe",
    version="2.0.0",
    author="Rodolfo",
    author_email="rodolfonobregar@gmail.com",
    description="Cross-platform audio transcription with LLM processing",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rodolfonobrega/audioscribe",
    project_urls={
        "Bug Reports": "https://github.com/rodolfonobrega/audioscribe/issues",
        "Source": "https://github.com/rodolfonobrega/audioscribe",
        "Documentation": "https://audioscribe.readthedocs.io/",
    },
    packages=find_packages(exclude=["tests", "tests.*", "docs", "docs.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Sound/Audio :: Speech",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.7.0",
            "isort>=5.12.0",
            "mypy>=1.5.0",
            "flake8>=6.1.0",
        ],
        "audio": [
            "pyaudio>=0.2.13",
        ],
        "windows": [
            "pywin32>=306",
        ],
    },
    entry_points={
        "console_scripts": [
            "audioscribe=main:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    keywords="transcription speech audio llm groq whisper cross-platform",
)
