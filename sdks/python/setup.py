from setuptools import setup, find_packages

setup(
    name="ai-empire",
    version="4.0.0",
    description="AI Empire Python SDK",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    author="Grupo AN Development",
    author_email="contact@grupoan.dev",
    url="https://github.com/GrupoANDevelopment-m/ai-empire",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=["httpx>=0.27"],
    extras_require={
        "all": ["numpy", "pandas"],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
