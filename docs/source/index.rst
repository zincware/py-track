.. ZnTrack documentation master file, created by
   sphinx-quickstart on Mon Jun  7 17:11:53 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to ZnTrack's documentation!
===================================
ZnTrack is `zincwarecode's <https://zincwarecode.com>`_ first developer package
and in fact, the first released on PyPi, so we are glad you are here.
ZnTrack is built to help you write code that can easily be shared and reproduced.
It uses `Data Version Control <https://dvc.org/>`_ to track generated files and parameters.
ZnTrack is designed as a developer package aiming to be used in other software packages.
If you are not planning on writing such packages we highly recommend looking up DVC first.

ZnTrack might still be helpful for you as it provides an Object-Relational Mapping for DVC in Python.
Additionally, it provides an experimental feature that enables the usage of Python classes
from within a Jupyter Notebook while utilizing DVC tracking.
Please have a look at the Tutorials and Documentation for detailed
information or write an issue on Github for https://github.com/zincware/ZnTrack

.. toctree::
   :maxdepth: 1
   :caption: First Steps:

   installation

.. toctree::
   :maxdepth: 1
   :caption: User Guide:

   _overview/01_Intro.ipynb
   _overview/02_PassingClasses.ipynb
   _overview/03_dependencies.ipynb
   _overview/04_metrics_and_plots.ipynb
   _overview/05_metadata.ipynb
   _overview/06_named_nodes.ipynb
   _overview/OptionalDVC.ipynb
   jupyter.rst

.. toctree::
   :maxdepth: 1
   :caption: Theory:

   _theory/directed_acyclic_graphs

.. toctree::
   :maxdepth: 1
   :caption: Examples:

   tutorials

.. toctree::
   :maxdepth: 1
   :caption: Migration to v0.3:

   _tutorials/migration_guide_v3


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
