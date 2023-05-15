import os
import shutil
import sys
import subprocess
import platform
import uuid
from platform import python_version

import logging

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    datefmt="%c",
)
# Mute numexpr threads info
logging.getLogger("numexpr").setLevel(logging.WARNING)

from .compile import PACKAGE_PATH

## Variables for alphafold module
ALPHAFOLD_GIT_REPO = "https://github.com/deepmind/alphafold"
ALPHAFOLD_GIT_REPO_VERSION = "main"  # Get version currently hosted on main branch
PDBFIXER_GIT_REPO = "https://github.com/openmm/pdbfixer.git"
# Unique ID to name temporary jackhmmer folder
UUID = "fcb45c67-8b27-4156-bbd8-9d11512babf2"
# # Path to temporary mounted disk (global)
# TMP_DISK = ""
# Model parameters
PARAMS_URL = (
    "https://storage.googleapis.com/alphafold/alphafold_params_colab_2022-12-06.tar"
)
PARAMS_DIR = os.path.join(PACKAGE_PATH, "bins/alphafold/")
PARAMS_PATH = os.path.join(PARAMS_DIR, "params_temp.tar")


def setup(module):
    """
    Function to install third-party dependencies for a specified gget module.
    Requires pip to be installed (https://pip.pypa.io/en/stable/installation).

    Args:
    - module    (str) gget module for which dependencies should be installed, e.g. "alphafold", "cellxgene" or "gpt".
    """
    supported_modules = ["alphafold", "cellxgene", "gpt"]
    if module not in supported_modules:
        raise ValueError(
            f"'module' argument specified as {module}. Expected one of: {', '.join(supported_modules)}"
        )

    if module == "gpt":
        logging.info("Installing openai package (requires pip).")
        command = "pip install -U openai"
        with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
            stderr = process.stderr.read().decode("utf-8")
        # Exit system if the subprocess returned with an error
        if process.wait() != 0:
            if stderr:
                # Log the standard error if it is not empty
                sys.stderr.write(stderr)
            logging.error(
                "openai installation with pip (https://pypi.org/project/openai) failed."
            )
            return

        try:
            import openai

            logging.info(f"openai installed succesfully.")
        except ImportError:
            logging.error(
                "openai installation with pip (https://pypi.org/project/openai) failed."
            )
            return

    if module == "cellxgene":
        logging.info("Installing cellxgene-census package (requires pip).")
        command = "pip install -U cellxgene-census"
        with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
            stderr = process.stderr.read().decode("utf-8")
        # Exit system if the subprocess returned with an error
        if process.wait() != 0:
            if stderr:
                # Log the standard error if it is not empty
                sys.stderr.write(stderr)
            logging.error(
                "cellxgene-census installation with pip (https://pypi.org/project/cellxgene-census) failed."
            )
            return

        try:
            import cellxgene_census

            logging.info(f"cellxgene_census installed succesfully.")
        except ImportError:
            logging.error(
                "cellxgene-census installation with pip (https://pypi.org/project/cellxgene-census) failed."
            )
            return

    if module == "alphafold":
        if platform.system() == "Windows":
            logging.warning(
                "gget setup alphafold and gget alphafold are not supported on Windows OS."
            )

        ## Ask user to install openmm if not already installed
        try:
            import simtk.openmm as openmm

            # Silence openmm logger
            logging.getLogger("openmm").setLevel(logging.WARNING)

            # Commenting the following out because openmm v7.7.0 does not support __version__
            # # Check if correct version was installed
            # if openmm.__version__ != "7.5.1":
            #     raise ImportError()

            # logging.info(f"openmm v{openmm.__version__} already installed.")

        except ImportError as e:
            raise ImportError(
                f"""
                Importing openmm resulted in the following error:
                {e}

                Please install AlphaFold third-party dependency openmm v7.5.1 (or v7.7.0 for Python >= 3.10) by running the following command from the command line: 
                'conda install -qy conda==4.13.0 && conda install -qy -c conda-forge openmm=7.5.1'   (or 'openmm=7.7.0' for Python >= 3.10)
                (Recommendation: Follow with 'conda update -qy conda' to update conda to the latest version afterwards.)
                """
            )

        ## Install py3Dmol
        logging.info("Installing py3Dmol (requires pip).")
        command = "pip install py3Dmol>=1.8.0"
        with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
            stderr = process.stderr.read().decode("utf-8")
        # Exit system if the subprocess returned with an error
        if process.wait() != 0:
            if stderr:
                # Log the standard error if it is not empty
                sys.stderr.write(stderr)
            logging.error(
                "py3Dmol>=1.8.0 installation with pip (https://pypi.org/project/py3Dmol) failed."
            )
            return

        # Test installation
        try:
            import py3Dmol

            logging.info(f"py3Dmol installed succesfully.")
        except ImportError:
            logging.error(
                "py3Dmol installation with pip (https://pypi.org/project/py3Dmol/) failed."
            )
            return

        ## Install Alphafold if not already installed
        logging.info("Installing AlphaFold from source (requires pip and git).")

        ## Install AlphaFold and change jackhmmer directory where database chunks are saved in
        # Define AlphaFold folder name and location
        alphafold_folder = os.path.join(
            PACKAGE_PATH, "tmp_alphafold_" + str(uuid.uuid4())
        )

        # Clone AlphaFold github repo
        # Replace directory where jackhmmer database chunks will be saved
        # Insert "logging.set_verbosity(logging.WARNING)" to mute all info loggers
        # Pip install AlphaFold from local directory
        if platform.system() == "Darwin":
            command = """
                git clone --branch main -q --branch {} {} {} \
                && sed -i '' 's/\/tmp\/ramdisk/{}/g' {}/alphafold/data/tools/jackhmmer.py \
                && sed -i '' 's/from absl import logging/from absl import logging\\\nlogging.set_verbosity(logging.WARNING)/g' {}/alphafold/data/tools/jackhmmer.py \
                && pip install -q -r {}/requirements.txt \
                && pip install -q --no-dependencies {}
                """.format(
                ALPHAFOLD_GIT_REPO_VERSION,
                ALPHAFOLD_GIT_REPO,
                alphafold_folder,
                os.path.expanduser(f"~/tmp/jackhmmer/{UUID}").replace(
                    "/", "\/"
                ),  # Replace directory where jackhmmer database chunks will be saved
                alphafold_folder,
                alphafold_folder,
                alphafold_folder,
                alphafold_folder,
            )
        else:
            command = """
                git clone --branch main -q --branch {} {} {} \
                && sed -i 's/\/tmp\/ramdisk/{}/g' {}/alphafold/data/tools/jackhmmer.py \
                && sed -i 's/from absl import logging/from absl import logging\\\nlogging.set_verbosity(logging.WARNING)/g' {}/alphafold/data/tools/jackhmmer.py \
                && pip install -q -r {}/requirements.txt \
                && pip install -q --no-dependencies {}
                """.format(
                ALPHAFOLD_GIT_REPO_VERSION,
                ALPHAFOLD_GIT_REPO,
                alphafold_folder,
                os.path.expanduser(f"~/tmp/jackhmmer/{UUID}").replace(
                    "/", "\/"
                ),  # Replace directory where jackhmmer database chunks will be saved
                alphafold_folder,
                alphafold_folder,
                alphafold_folder,
                alphafold_folder,
            )

        with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
            stderr = process.stderr.read().decode("utf-8")
        # Exit system if the subprocess returned with an error
        if process.wait() != 0:
            if stderr:
                # Log the standard error if it is not empty
                sys.stderr.write(stderr)
            logging.error("AlphaFold installation failed.")
            return

        # Remove cloned directory
        shutil.rmtree(alphafold_folder)

        try:
            import alphafold as AlphaFold

            logging.info(f"AlphaFold installed succesfully.")
        except ImportError:
            logging.error("AlphaFold installation failed.")
            return

        ## Append AlphaFold to path
        alphafold_path = os.path.abspath(os.path.dirname(AlphaFold.__file__))
        if alphafold_path not in sys.path:
            sys.path.append(alphafold_path)

        ## Install pdbfixer
        logging.info("Installing pdbfixer from source (requires pip and git).")

        pdbfixer_folder = os.path.join(
            PACKAGE_PATH, "tmp_pdbfixer_" + str(uuid.uuid4())
        )

        try:
            if openmm.__version__ == "7.5.1":
                # Install pdbfixer version compatible with openmm v7.5.1
                PDBFIXER_VERSION = "v1.7"
        except:
            PDBFIXER_VERSION = "v1.8.1" # Latest: v1.9

        command = f"""
            git clone -q --branch {PDBFIXER_VERSION} {PDBFIXER_GIT_REPO} {pdbfixer_folder} \
            && pip install -q {pdbfixer_folder} \
            """

        with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
            stderr = process.stderr.read().decode("utf-8")
        # Exit system if the subprocess returned with an error
        if process.wait() != 0:
            if stderr:
                # Log the standard error if it is not empty
                sys.stderr.write(stderr)
            logging.error("pdbfixer installation failed.")
            return

        # Remove cloned directory
        shutil.rmtree(pdbfixer_folder)

        # Check if pdbfixer was installed successfully
        command = "pip list | grep pdbfixer"
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        pdb_out, err = process.communicate()

        if pdb_out.decode() != "":
            logging.info(f"pdbfixer installed succesfully.")
        else:
            logging.error("pdbfixer installation failed.")
            return

        ## Download model parameters
        # Download parameters if the params directory is empty
        if not os.path.exists(os.path.join(PARAMS_DIR, "params/")):
            # Create folder to save parameter files
            os.makedirs(os.path.join(PARAMS_DIR, "params/"), exist_ok=True)

        if len(os.listdir(os.path.join(PARAMS_DIR, "params/"))) < 12:
            logging.info(
                "Downloading AlphaFold model parameters (requires 4.1 GB of storage). This might take a few minutes."
            )
            if platform.system() == "Windows":
                # The double-quotation marks allow white spaces in the path, but this does not work for Windows
                command = f"""
                    curl -# -o {PARAMS_PATH} {PARAMS_URL} \
                    && tar --extract --file={PARAMS_PATH} --directory={PARAMS_DIR+'params/'} --preserve-permissions \
                    && rm {PARAMS_PATH}
                    """
            else:
                command = f"""
                    curl -# -o '{PARAMS_PATH}' '{PARAMS_URL}' \
                    && tar --extract --file='{PARAMS_PATH}' --directory='{PARAMS_DIR+'params/'}' --preserve-permissions \
                    && rm '{PARAMS_PATH}'
                    """

            with subprocess.Popen(
                command, shell=True, stderr=subprocess.PIPE
            ) as process:
                stderr = process.stderr.read().decode("utf-8")
                # Log the standard error if it is not empty
                if stderr:
                    sys.stderr.write(stderr)
            # Exit system if the subprocess returned with an error
            if process.wait() != 0:
                logging.error("Model parameter download failed.")
                return
            else:
                logging.info("Model parameter download complete.")
        else:
            logging.info("AlphaFold model parameters already downloaded.")
