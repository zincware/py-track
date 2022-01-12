|build| |docs| |license| |code style| |coverage|

.. image:: https://raw.githubusercontent.com/zincware/ZnTrack/main/docs/source/img/zntrack.png

Parameter Tracking for Python
-----------------------------
ZnTrack [zɪŋk træk] is an easy-to-use package for tracking parameters in your Python
projects.
What is a parameter? Anything set by a user in your code, for example, the number of
layers in a neural network layer or the window size of a moving average.
ZnTrack works by storing the values of parameters in Python classes and functions and
monitoring how they change for several different runs.
These changes can then be compared graphically to see what effect they had on your
workflow.
Beyond the standard tracking of parameters in a project, ZnTrack can be used to deploy
jobs with a set of different parameter values, avoid the re-running of components of code
where parameters have not changed, and to identify computational bottlenecks in your
code.

Example
========
With ZnTrack a DVC Node on the computational graph can be written as a Python class.
DVC Options, such as parameters, input dependencies and output files are class attributes.

.. code-block:: py

    from zntrack import Node, zn
    from random import randrange

    class HelloWorld(Node):
        """Define a ZnTrack Node"""
        # parameter to be tracked
        max_number = zn.params()
        # parameter to store as output
        random_number = zn.outs()

        def __init__(self, max_number=None):
            """Pass tracked arguments"""
            self.max_number = max_number

        def run(self):
            """Command to be run by DVC"""
            self.random_number = randrange(self.max_number)

This Node can then be saved as a DVC stage

.. code-block:: py

    HelloWorld(max_number=512).write_dvc()

which builds the DVC stage and can be used e.g., through :code:`dvc repro`.
The results can then be accessed easily via :code:`HelloWorld.load().random_number`.

More detailed examples and further information can be found in the `ZnTrack Documentation <https://zntrack.readthedocs.io/en/latest/>`_.

Technical Details
=================

ZnTrack as an Object-Relational Mapping for DVC
-----------------------------------------------

On a fundamental level the ZnTrack package provides an easy-to-use interface for DVC directly from Python.
It handles all the computational overhead of reading config files, defining outputs in the `dvc.yaml` as well as in the script and much more.

For more information on DVC visit their `homepage <https://dvc.org/doc>`_.


Installation
============

Simply run:

.. code-block:: bash

   pip install zntrack

Or you can install from source with:

.. code-block:: bash

   git clone https://github.com/zincware/ZnTrack.git
   cd ZnTrack
   pip install .

.. badges

.. |build| image:: https://github.com/zincware/ZnTrack/actions/workflows/pytest.yaml/badge.svg
    :alt: Build tests passing
    :target: https://github.com/zincware/py-test/blob/readme_badges/

.. |docs|  image:: https://readthedocs.org/projects/zntrack/badge/?version=latest
    :target: https://zntrack.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status

.. |license| image:: https://img.shields.io/badge/License-EPL-purple.svg?style=flat
    :alt: Project license
    :target: https://www.eclipse.org/legal/epl-2.0/faq.php

.. |code style| image:: https://img.shields.io/badge/code%20style-black-black
    :alt: Code style: black
    :target: https://github.com/psf/black/
    
.. |coverage| image:: https://coveralls.io/repos/github/zincware/ZnTrack/badge.svg
    :alt: Code coverage
    :target: https://coveralls.io/github/zincware/ZnTrack

