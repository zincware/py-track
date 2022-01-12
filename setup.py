import pathlib

import setuptools

long_description = pathlib.Path("README.rst").read_text()
required_packages = pathlib.Path("requirements.txt").read_text().splitlines()

setuptools.setup(
    name="zntrack",
    version="0.3.0",
    author="zincwarecode",
    author_email="zincwarecode@gmail.com",
    description="A Python package for parameter and data version control with DVC",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/zincware/ZnTrack",
    download_url="https://github.com/zincware/ZnTrack/archive/beta.tar.gz",
    keywords=["dvc", "machine learning", "parameter tracking"],
    packages=setuptools.find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Eclipse Public License 2.0 (EPL-2.0)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=required_packages,
)
