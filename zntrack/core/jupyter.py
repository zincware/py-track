import logging

log = logging.getLogger(__name__)
import pathlib
import re
import subprocess

from zntrack.utils.config import config


def jupyter_class_to_file(silent, nb_name, module_name):
    """Extract the class definition form a ipynb file"""

    log.warning(
        "Jupyter support is an experimental feature! Please save your "
        "notebook before running this command!\n"
        "Submit issues to https://github.com/zincware/ZnTrack."
    )
    log.warning(f"Converting {nb_name} to file {module_name}.py")

    nb_name = pathlib.Path(nb_name)

    if silent:
        _ = subprocess.run(
            ["jupyter", "nbconvert", "--to", "script", nb_name],
            capture_output=True,
        )
    else:
        subprocess.run(["jupyter", "nbconvert", "--to", "script", nb_name])

    reading_class = False

    imports = ""

    class_definition = ""

    with pathlib.Path(nb_name).with_suffix(".py").open("r") as f:
        for line in f:
            if line.startswith("import") or line.startswith("from"):
                imports += line
            if reading_class:
                if (
                    re.match(r"\S", line)
                    and not line.startswith("#")
                    and not line.startswith("class")
                ):
                    reading_class = False
            if reading_class or line.startswith("class"):
                reading_class = True
                class_definition += line
            if line.startswith("@Node"):
                reading_class = True
                class_definition += "@Node()\n"

    src = imports + "\n\n" + class_definition

    src_file = pathlib.Path(config.nb_class_path, module_name).with_suffix(".py")
    config.nb_class_path.mkdir(exist_ok=True, parents=True)

    src_file.write_text(src)

    # Remove converted ipynb file
    nb_name.with_suffix(".py").unlink()
