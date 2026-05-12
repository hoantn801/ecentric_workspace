from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# get version from __version__ variable in ecentric_workspace/__init__.py
from ecentric_workspace import __version__ as version

setup(
    name="ecentric_workspace",
    version=version,
    description="Employee portal + approval workflow for eCentric",
    author="eCentric",
    author_email="it@ecentric.vn",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires
)
