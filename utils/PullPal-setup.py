from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="pullpal",
    version="0.1.0",
    author="Frederick Pellerin",
    author_email="fredp3d@proton.me",
    description="A tool for fetching and saving complete GitHub pull request conversations",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/TheRealFREDP3D/PullPal",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=[
        "requests",
        "python-dotenv",
    ],
    entry_points={
        "console_scripts": [
            "pullpal=pullpal.PullPal:main",
        ],
    },
)
