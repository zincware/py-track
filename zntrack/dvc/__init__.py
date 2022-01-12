"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description: Collection of DVC options

Based on ZnTrackOption python descriptors this gives access to them being used
to define e.g. dependencies

Examples
--------

>>> @Node()
>>> class HelloWorld
>>>     vars = dvc.params()
"""
import logging

from zntrack.core.parameter import ZnTrackOption
from zntrack.descriptor import Metadata

log = logging.getLogger(__name__)


# All available DVC cmd options + results
# detailed explanations on https://dvc.org/doc/command-reference/run#options


class params(ZnTrackOption):
    # depreciated
    metadata = Metadata(dvc_option="params", zntrack_type="params")


class deps(ZnTrackOption):
    # depreciated
    metadata = Metadata(dvc_option="deps", zntrack_type="deps")


class outs(ZnTrackOption):
    metadata = Metadata(dvc_option="outs", zntrack_type="dvc")


class outs_no_cache(ZnTrackOption):
    metadata = Metadata(dvc_option="outs_no_cache", zntrack_type="dvc")


class outs_persistent(ZnTrackOption):
    metadata = Metadata(dvc_option="outs_persistent", zntrack_type="dvc")


class metrics(ZnTrackOption):
    metadata = Metadata(dvc_option="metrics", zntrack_type="dvc")


class metrics_no_cache(ZnTrackOption):
    metadata = Metadata(dvc_option="metrics_no_cache", zntrack_type="dvc")


class plots(ZnTrackOption):
    metadata = Metadata(dvc_option="plots", zntrack_type="dvc")


class plots_no_cache(ZnTrackOption):
    metadata = Metadata(dvc_option="plots_no_cache", zntrack_type="dvc")
