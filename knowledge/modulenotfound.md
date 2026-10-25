Title: ModuleNotFoundError (Python)
Source: https://docs.python.org/3/library/exceptions.html
Keywords: modulenotfounderror, no module named, importerror, import error, pip install, python, numpy, virtual environment

ModuleNotFoundError is raised when Python cannot find a module you tried to import. It is a subclass of ImportError.
Common causes: the package is not installed, it is installed in a different Python environment than the one running your code, the name is misspelled (package and import names can differ), or a local file shadows the module name.
Ways to investigate: run python -m pip install <package> using the same python that runs your script, check which interpreter is active with python --version and where python (Windows), and confirm the virtual environment is activated.