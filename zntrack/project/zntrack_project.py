"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html
SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the Zincware Project.

Description: The class for the ZnTrackProject
"""
import logging
import subprocess
from datetime import datetime

from zntrack.interface import DVCInterface

log = logging.getLogger(__name__)


class ZnTrackProject(DVCInterface):
    """Node Project to handle experiments via subprocess calls to DVC"""

    def __init__(self, name: str = None):
        """

        Parameters
        ----------
        name: str (optional)
            Name of the project
        """
        super().__init__()
        if name is None:
            name = f'PyTrackProject_{datetime.now().strftime("%Y_%m_%d-%H_%M_%S")}'
        self.name = name

    def queue(self, name: str = None):
        """Add this project to the DVC queue"""
        if name is not None:
            self.name = name
        log.info("Running git add")
        subprocess.check_call(["git", "add", "."])
        log.info("Queue DVC stage")
        subprocess.check_call(["dvc", "exp", "run", "--name", self.name, "--queue"])

    @staticmethod
    def remove_queue():
        """Empty the queue"""
        log.warning("Removing all queried experiments!")
        subprocess.check_call(["dvc", "exp", "remove", "--queue"])

    @staticmethod
    def run_all():
        """Run all queried experiments"""
        log.info("RUN DVC stage")
        subprocess.check_call(["dvc", "exp", "run", "--run-all"])
        log.info("Running git add")
        subprocess.check_call(["git", "add", "."])

    def run(self, name: str = None):
        """Add this experiment to the queue and run the full queue"""
        self.queue(name=name)
        self.run_all()
        for x in range(3):
            try:
                self.load(name=name)
            except subprocess.CalledProcessError as e:
                # sometimes it takes more than one trial (windows)
                if x == 2:
                    raise e
        log.info("Finished")

    def load(self, name=None):
        """Load this project"""
        if name is not None:
            self.name = name
        subprocess.check_call(["dvc", "exp", "apply", self.name])

    def save(self):
        """Save this project to a branch"""
        subprocess.check_call(["dvc", "exp", "branch", self.name, self.name])

    def create_dvc_repository(self):
        """Perform git and dvc init"""
        try:
            subprocess.check_call(
                ["dvc", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            log.info("DVC repository already exists.")
        except subprocess.CalledProcessError:
            log.info("Setting up GIT/DVC repository.")
            subprocess.check_call(
                ["git", "init"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.check_call(
                ["dvc", "init"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.check_call(
                ["git", "add", "."],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.check_call(
                ["git", "commit", "-m", f"Initialize {self.name}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    @staticmethod
    def _destroy():
        """Remove the DVC directory"""
        subprocess.check_call(["dvc", "destroy", "-f"])

    @staticmethod
    def repro():
        """Run dvc repro"""
        subprocess.check_call(["dvc", "repro"])
