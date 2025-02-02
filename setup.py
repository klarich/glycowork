import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="glycowork",
    version="0.6.0",
    author="Daniel Bojar",
    author_email="daniel.bojar@gu.se",
    description="Package for processing and analyzing glycans",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/BojarLab/glycowork",
    packages=setuptools.find_packages(),
    include_package_data=True,
    package_data={'': ['*.csv', '*.pkl', '*.jpg', '*.pt']},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
    install_requires=["scikit-learn", "regex", "networkx",
                      "statsmodels", "scipy", "torch",
                      "seaborn", "xgboost", "mpld3",
                      "requests", "pandas", "glyles",
                      "pubchempy", "matplotlib-inline",
                      "python-louvain"],
)
