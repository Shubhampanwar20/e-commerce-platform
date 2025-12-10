"""
Setup file for building Cython extension
"""
from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy

extensions = [
    Extension(
        "cython_recommendations",
        ["cython_recommendations.pyx"],
        include_dirs=[numpy.get_include()],
        extra_compile_args=["-O3"],
    )
]

setup(
    ext_modules=cythonize(extensions, compiler_directives={'language_level': "3"}),
    zip_safe=False,
)

