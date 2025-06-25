from setuptools import setup

setup(
  name="zap",
  version="1.0",
  py_modules=["zap"],
  entry_points={
     "console_scripts": ["zap=zap:main"],
  },
)
