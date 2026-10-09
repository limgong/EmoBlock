from setuptools import Extension, setup
from Cython.Build import cythonize

setup(ext_modules=cythonize(
    [Extension('emoblocks_json_native', ['emoblocks_json_native.pyx'])],
    compiler_directives={'language_level': 3},
))
