"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description: Function decorator for ZnTrack
"""

import dataclasses
import logging
import pathlib
import subprocess
import typing

import dot4dict
import znipy.utils

from zntrack.core.dvcgraph import DVCRunOptions
from zntrack.utils import config, file_io, utils

StrOrPath = typing.Union[str, pathlib.Path]

log = logging.getLogger(__name__)


@dataclasses.dataclass
class NodeConfig:
    """DataClass to contain the arguments passed by the user

    Attributes
    ----------
    All dvc attributes but connected by "_" instead of "-"

    """

    deps: typing.Union[StrOrPath, typing.List[StrOrPath]] = None
    outs: typing.Union[StrOrPath, typing.List[StrOrPath]] = None
    outs_no_cache: typing.Union[StrOrPath, typing.List[StrOrPath]] = None
    outs_persist: typing.Union[StrOrPath, typing.List[StrOrPath]] = None
    outs_persist_no_cache: typing.Union[StrOrPath, typing.List[StrOrPath]] = None
    metrics: typing.Union[StrOrPath, typing.List[StrOrPath]] = None
    metrics_no_cache: typing.Union[StrOrPath, typing.List[StrOrPath]] = None
    plots: typing.Union[StrOrPath, typing.List[StrOrPath]] = None
    plots_no_cache: typing.Union[StrOrPath, typing.List[StrOrPath]] = None

    params: typing.Union[dot4dict.dotdict, dict] = dataclasses.field(default_factory=dict)

    def write_dvc_command(self, node_name: str) -> list:
        """Collect dvc commands

        Parameters
        ----------
        node_name:str
            name of the node, usually func.__name__

        Returns
        -------
        list: a list of all options like
        ["--outs", "outs.txt", "--params", "params.yaml:<node_name>", ...]
        handling lists of files as well the parameters

        """
        script = []
        if self.params is not None:
            if len(self.params) > 0:
                script += ["--params", f"params.yaml:{node_name}"]
        for field in self.__dataclass_fields__:
            if field == "params":
                continue
            if isinstance(getattr(self, field), (list, tuple)):
                for element in getattr(self, field):
                    script += [f"--{field.replace('_', '-')}", str(element)]
            elif getattr(self, field) is not None:
                script += [f"--{field.replace('_', '-')}", str(getattr(self, field))]

        return script


AnyOrNodeConfig = typing.Union[typing.Any, NodeConfig]
UnionListOrStrAndPath = typing.Union[typing.List[StrOrPath], StrOrPath]


def nodify(
    *,
    params: dict = None,
    outs: UnionListOrStrAndPath = None,
    outs_no_cache: UnionListOrStrAndPath = None,
    outs_persist: UnionListOrStrAndPath = None,
    outs_persist_no_cache: UnionListOrStrAndPath = None,
    metrics: UnionListOrStrAndPath = None,
    metrics_no_cache: UnionListOrStrAndPath = None,
    deps: UnionListOrStrAndPath = None,
    plots: UnionListOrStrAndPath = None,
    plots_no_cache: UnionListOrStrAndPath = None,
):
    """Main wrapper Function to convert a function into a DVC Stage

    Parameters
    ----------
    params: dict
        for the params.yaml file context
    **kwargs: str|Path|list
        All other parameters are related to dvc run commands and can be a str / Path
        or a list of them

    References
    ----------
    https://dvc.org/doc/command-reference/run#options
    """
    if not isinstance(params, dict) and params is not None:
        raise ValueError("Parameter must be dict or dot4dict.dotdict.")

    # Check that the given type is correct
    # TODO consider adding this to NodeConfig in the future
    for option in [
        outs,
        outs_no_cache,
        outs_persist,
        outs_persist_no_cache,
        metrics,
        metrics_no_cache,
        deps,
        plots,
        plots_no_cache,
    ]:
        if not utils.check_type(
            option, (str, pathlib.Path), allow_iterable=True, allow_none=True
        ):
            raise ValueError(
                f"{option} is not a supported type. "
                "Please use single values or lists of <str> and <pathlib.Path>."
            )

    def func_collector(func):
        """Required for decorator to work"""

        def wrapper(
            *,
            silent: bool = False,
            nb_name: str = None,
            no_commit: bool = False,
            external: bool = False,
            always_changed: bool = False,
            no_exec: bool = True,
            force: bool = True,
            no_run_cache: bool = False,
            dry_run: bool = False,
            run: bool = None,
            exec_func=False,
        ) -> AnyOrNodeConfig:
            """Wrap the function

            Parameters
            ----------
            exec_func: bool
                Set to true to execute the function core
            silent: bool
                If called with no_exec=False this allows to hide the output from the
                subprocess call.
            nb_name: str
                Notebook name when not using config.nb_name (this is not recommended)
            no_commit: dvc parameter
            external: dvc parameter
            always_changed: dvc parameter
            no_exec: dvc parameter
            run: bool, inverse of no_exec. Will overwrite no_exec if set.
            force: dvc parameter
            no_run_cache: dvc parameter
            dry_run: bool, default = False
                Only return the script but don't actually run anything

            Returns
            -------
            This function only returns the parsed_func when exec_func is True, otherwise
            it returns the NodeConfig

            """
            if run is not None:
                no_exec = not run

            if nb_name is None:
                nb_name = config.nb_name

            # Jupyter Notebook
            if nb_name is not None:
                module = f"{config.nb_class_path}.{func.__name__}"

                znipy.utils.jupyter_class_to_file(
                    silent=silent,
                    nb_name=nb_name,
                    module_name=func.__name__,
                    nb_class_path=config.nb_class_path,
                )
            else:
                module = utils.module_handler(func)

            cfg_file = pathlib.Path("zntrack.json")
            params_file = pathlib.Path("params.yaml")
            if exec_func:
                # TODO should exec_func always load from file or check if values
                #  are passed and then update the files?
                cfg_file_content = file_io.read_file(cfg_file)[func.__name__]
                cfg_file_content = utils.decode_dict(cfg_file_content)
                params_file_content = file_io.read_file(params_file)[func.__name__]
                cfg_file_content["params"] = params_file_content

                cfg = NodeConfig(**cfg_file_content)
                cfg.params = dot4dict.dotdict(cfg.params)
                return func(cfg)
            else:
                cfg = NodeConfig(
                    outs=outs,
                    params=params,
                    deps=deps,
                    outs_no_cache=outs_no_cache,
                    outs_persist=outs_persist,
                    outs_persist_no_cache=outs_persist_no_cache,
                    metrics=metrics,
                    metrics_no_cache=metrics_no_cache,
                    plots=plots,
                    plots_no_cache=plots_no_cache,
                )
                for value_name, value in dataclasses.asdict(cfg).items():
                    if value_name == "params":
                        file_io.update_config_file(
                            file=params_file,
                            node_name=func.__name__,
                            value_name=None,
                            value=value,
                        )
                    else:
                        file_io.update_config_file(
                            file=cfg_file,
                            node_name=func.__name__,
                            value_name=value_name,
                            value=value,
                        )

            script = ["dvc", "run", "-n", func.__name__]
            script += DVCRunOptions(
                no_commit=no_commit,
                external=external,
                always_changed=always_changed,
                no_run_cache=no_run_cache,
                no_exec=no_exec,
                force=force,
            ).dvc_args

            script += cfg.write_dvc_command(func.__name__)

            if nb_name is not None:
                script += [
                    "--deps",
                    pathlib.Path(*module.split(".")).with_suffix(".py").as_posix(),
                ]

            import_str = f"""python -c "from {module} import {func.__name__};"""
            import_str += f"""{func.__name__}(exec_func=True)" """
            script += [import_str]
            log.debug(f"Running script: {script}")
            if dry_run:
                return script
            subprocess.check_call(script)

            cfg.params = dot4dict.dotdict(cfg.params)
            return cfg

        return wrapper

    return func_collector
