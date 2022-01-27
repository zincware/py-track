"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description:
"""

from time import time

from zntrack.metadata.base import MetaData


class TimeIt(MetaData):
    """TimeIt decorator that saves the execution time of decorated method"""

    name_of_metric = "timeit"

    def __call__(self, cls, *args, **kwargs):
        """Measure the execution time by storing the time
        before and after the function call
        """
        start_time = time()
        parsed_func = self.func(cls, *args, **kwargs)
        stop_time = time()

        self.save_metadata(cls, value=stop_time - start_time)

        return parsed_func
