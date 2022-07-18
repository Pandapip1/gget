from datetime import date
import tqdm.notebook
import os
import sys
import subprocess
import platform
import collections
import copy
from concurrent import futures
import random
from urllib import request
import matplotlib.pyplot as plt
import numpy as np
from IPython import display
from ipywidgets import GridspecLayout
from ipywidgets import Output

import logging

# Add and format time stamp in logging messages
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    datefmt="%c",
)
# Mute numexpr threads info
logging.getLogger("numexpr").setLevel(logging.WARNING)
# Mute jackhmmer info
logging.getLogger("jackhmmer").setLevel(logging.WARNING)
# Mute alphafold info
logging.getLogger("alphafold").setLevel(logging.WARNING)

TQDM_BAR_FORMAT = (
    "{l_bar}{bar}| {n_fmt}/{total_fmt} [elapsed: {elapsed} remaining: {remaining}]"
)

from .compile import PACKAGE_PATH

# PACKAGE_PATH = "/Users/lauraluebbert/Downloads/gget"

ALPHAFOLD_GIT_REPO = "https://github.com/deepmind/alphafold"
PDBFIXER_GIT_REPO = "https://github.com/openmm/pdbfixer.git"

PARAMS_URL = (
    "https://storage.googleapis.com/alphafold/alphafold_params_colab_2022-03-02.tar"
)
PARAMS_DIR = os.path.join(PACKAGE_PATH, f"bins/alphafold/")
PARAMS_PATH = os.path.join(PARAMS_DIR, "params_temp.tar")

STEREO_CHEM_DIR = os.path.join(PARAMS_DIR, "stereo_chemical_props.txt")

JACKHMMER_BINARY_PATH = (
    f"/Users/lauraluebbert/Downloads/gget/gget/bins/{platform.system()}/jackhmmer"
)

# Global variable, temporary disk name for TMPFS (empty string)
TMP_DISK = ""

# Test pattern to find closest source
test_url_pattern = (
    "https://storage.googleapis.com/alphafold-colab{:s}/latest/uniref90_2021_03.fasta.1"
)

# Sequence validation parameters
MIN_SINGLE_SEQUENCE_LENGTH = 16
MAX_SINGLE_SEQUENCE_LENGTH = 2500
MAX_MULTIMER_LENGTH = 2500

# Maximum hits per database
MAX_HITS = {
    "uniref90": 10_000,
    "smallbfd": 5_000,
    "mgnify": 501,
    "uniprot": 50_000,
}

# Color bands for visualizing plddt
PLDDT_BANDS = [
    (0, 50, "#FF7D45"),
    (50, 70, "#FFDB13"),
    (70, 90, "#65CBF3"),
    (90, 100, "#0053D6"),
]


def plot_plddt_legend():
    """
    Function to plot the legend for pLDDT.
    """
    thresh = [
        "Very low (pLDDT < 50)",
        "Low (70 > pLDDT > 50)",
        "Confident (90 > pLDDT > 70)",
        "Very high (pLDDT > 90)",
    ]

    colors = [x[2] for x in PLDDT_BANDS]

    plt.figure(figsize=(2, 2))
    for c in colors:
        plt.bar(0, 0, color=c)
    plt.legend(thresh, frameon=False, loc="center", fontsize=20)
    plt.xticks([])
    plt.yticks([])
    ax = plt.gca()
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    plt.title("Model Confidence", fontsize=20, pad=20)

    return plt


def install_packages():
    """
    Function to install missing packages required to run gget alphafold.
    """
    # Define TMP_DISK as global variable
    global TMP_DISK

    ## Install openmm if not already installed
    try:
        import openmm

        # Check if correct version was installed
        if openmm.__version__ != "7.5.1" and openmm.__version__ != "7.6":
            raise ImportError()

        logging.info(f"openmm v{openmm.__version__} already installed.")

    except ImportError:
        logging.error(
            """
      Please install third-party dependency openmm v7.5.1 by running the following command from the command line:
      'conda install -c conda-forge openmm=7.5.1'
      """
        )
        return "error"

    ## Install Alphafold if not already installed
    try:
        import alphafold as AlphaFold

        logging.info(f"AlphaFold already installed.")

    except ImportError:
        logging.info("Installing AlphaFold from source (requires pip).")
        # Install AlphaFold and apply OpenMM patch.
        # command = f"""
        #     git clone {ALPHAFOLD_GIT_REPO} alphafold \
        #     && pip install --no-dependencies ./alphafold \
        #     && pushd {os.__file__.split('os.py')[0] + 'site-packages/'} \
        #     && patch -p0 < /content/alphafold/docker/openmm.patch \
        #     && popd \
        #     && rm -rf alphafold
        #     """
        # Install AlphaFold
        command = f"""
            git clone -q {ALPHAFOLD_GIT_REPO} alphafold \
            && pip install -q --no-dependencies ./alphafold \
            && rm -rf alphafold
            """

        with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
            stderr = process.stderr.read().decode("utf-8")
        # Exit system if the subprocess returned with an error
        if process.wait() != 0:
            if stderr:
                # Log the standard error if it is not empty
                sys.stderr.write(stderr)
            logging.error("AlphaFold installation failed.")
            return "error"

        try:
            import alphafold as AlphaFold

            logging.info(f"AlphaFold installed succesfully.")
        except ImportError:
            logging.error("AlphaFold installation failed.")
            return "error"

    ## Install pdbfixer if not already installed
    try:
        import pdbfixer

        logging.info(f"pdbfixer already installed.")

    except ImportError:
        logging.info("Installing pdbfixer from source (requires pip).")
        command = f"""
            git clone -q {PDBFIXER_GIT_REPO} pdbfixer && \
            pip install -q ./pdbfixer && \
            rm -rf pdbfixer
            """

        with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
            stderr = process.stderr.read().decode("utf-8")
        # Exit system if the subprocess returned with an error
        if process.wait() != 0:
            if stderr:
                # Log the standard error if it is not empty
                sys.stderr.write(stderr)
            logging.error("pdbfixer installation failed.")
            return "error"

        try:
            import pdbfixer

            logging.info(f"pdbfixer installed succesfully.")
        except ImportError:
            logging.error("pdbfixer installation failed.")
            return "error"

    ## Manage permission to jackhmmer binary
    command = f"chmod 755 {JACKHMMER_BINARY_PATH}"

    with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
        stderr = process.stderr.read().decode("utf-8")

    # Exit system if the subprocess returned with an error
    if process.wait() != 0:
        if stderr:
            # Log the standard error if it is not empty
            sys.stderr.write(stderr)
        logging.error("Giving chmod 755 permissions to jackhmmer binary failed.")
        return "error"

    # ## Create a temporary file system (TMPFS) to store a database chunk to make Jackhmmer run fast.
    # # TMPFS uses local memory for file system reads and writes, which is typically much faster than reads and writes in a UFS file system.
    # logging.info("Creating temporary file system (TMPFS) to store a database chunk and make Jackhmmer run faster.")
    # if platform.system() == "Linux":
    #   command = f"mkdir -m 777 -p /tmp/ramdisk && mount -t tmpfs -o size=9G ramdisk /tmp/ramdisk"

    #   with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
    #       stderr = process.stderr.read().decode("utf-8")

    #   # Exit system if the subprocess returned with an error
    #   if process.wait() != 0:
    #       # if stderr:
    #       # # Log the standard error if it is not empty
    #       # sys.stderr.write(stderr)
    #       logging.warning("Creating TMPFS failed. Jackhmmer will run slower.")

    # elif platform.system() == "Darwin":
    #   # Attach disk with 9GB
    #   command1 = "hdiutil attach -nomount ram://18432000"
    #   process = subprocess.Popen(command1, shell=True, stdout=subprocess.PIPE)
    #   out, err = process.communicate()

    #   # Record number of new disk
    #   TMP_DISK = out.decode("utf-8").strip()
    #   DISK_NUMBER = f"$({TMP_DISK} | tr -dc '0-9')"

    #   # Set up TMPFS
    #   command2 = f"newfs_hfs -v tmp /dev/rdisk{DISK_NUMBER}"
    #   command3 = f"diskutil eraseVolume HFS+ /tmp/ramdisk {TMP_DISK}"

    #   command = command2 + " && " + command3

    #   with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
    #     stderr = process.stderr.read().decode("utf-8")

    #   # Exit system if the subprocess returned with an error
    #   if process.wait() != 0:
    #       # if stderr:
    #       # # Log the standard error if it is not empty
    #       # sys.stderr.write(stderr)
    #       logging.warning("Creating TMPFS failed. Jackhmmer will run slower.")

    # else:
    command = "mkdir -p /tmp/ramdisk"

    with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
        stderr = process.stderr.read().decode("utf-8")
    # Exit system if the subprocess returned with an error
    if process.wait() != 0:
        if stderr:
            # Log the standard error if it is not empty
            sys.stderr.write(stderr)


def fetch(source):
    """
    Support function for finding closest source.
    """
    request.urlretrieve(test_url_pattern.format(source))
    return source


def get_msa(fasta_path, msa_databases, total_jackhmmer_chunks):
    """
    Function to search for MSA for the given sequence using chunked Jackhmmer search.
    """
    # Run the search against chunks of genetic databases to save disk space.
    raw_msa_results = collections.defaultdict(list)

    from alphafold.data.tools import jackhmmer

    with tqdm.notebook.tqdm(
        total=total_jackhmmer_chunks, bar_format=TQDM_BAR_FORMAT
    ) as pbar:
        # Set progress bar description
        pbar.set_description(f"Jackhmmer search")

        def jackhmmer_chunk_callback(i):
            pbar.update(n=1)

        for db_config in msa_databases:
            db_name = db_config["db_name"]
            jackhmmer_runner = jackhmmer.Jackhmmer(
                binary_path=JACKHMMER_BINARY_PATH,
                database_path=db_config["db_path"],
                get_tblout=True,
                num_streamed_chunks=db_config["num_streamed_chunks"],
                streaming_callback=jackhmmer_chunk_callback,
                z_value=db_config["z_value"],
            )
            # Group the results by database name.
            raw_msa_results[db_name].extend(jackhmmer_runner.query(fasta_path))

    return raw_msa_results


def clean_up():
    """
    Function to clean up temporary files after running gget alphafold.
    """
    # Remove fasta files with input sequences
    files = glob.glob("target_*.fasta")
    for f in files:
        try:
            os.remove(f)
        except:
            None

    # # Unmount temporary TMPFS
    # if platform.system() == "Linux":
    #   command = f"unmount /tmp/ramdisk"
    # elif platform.system() == "Darwin":
    #   # Detach last added disk
    #   command = f"hdiutil detach {TMP_DISK}"

    # if command:
    #   with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
    #     stderr = process.stderr.read().decode("utf-8")
    #     # Exit system if the subprocess returned with an error
    #     if process.wait() != 0:
    #         if stderr:
    #           # Log the standard error if it is not empty
    #           sys.stderr.write(stderr)


def alphafold(
    sequence,
    out=f"{str(date.today())}_gget_alphafold_prediction",
    run_relax=False,
    plot=True,
    show_sidechains=True,
):
    """
    Predicts the structure of a protein using a slightly simplified version of [AlphaFold v2.1.0](https://doi.org/10.1038/s41586-021-03819-2)
    published in the [AlphaFold Colab notebook](https://colab.research.google.com/github/deepmind/alphafold/blob/main/notebooks/AlphaFold.ipynb).

    Args:
      - sequence          Amino acid sequence (str), a list of sequences, or path to a FASTA file.
      - out               Path to folder to save prediction results in (str) or None.
                          Default: "[date]_gget_alphafold_prediction"
      - run_relax         True/False whether to AMBER relax the best model (default: False).
      - plot              True/False whether to provide a graphical overview of the prediction (default: True).
                          (Requires py3Dmol. Install with 'pip install py3Dmol'.)
      - show_sidechains   True/False whether to show side chains in the plot (default: True).

    Saves the predicted aligned error (json) and the prediction (PDB) in the defined 'out' folder.

    From the [AlphaFold Colab notebook](https://colab.research.google.com/github/deepmind/alphafold/blob/main/notebooks/AlphaFold.ipynb):
    "In comparison to AlphaFold v2.1.0, this Colab notebook uses no templates (homologous structures)
    and only a selected portion of the [BFD database](https://bfd.mmseqs.com/). We have validated these
    changes on several thousand recent PDB structures. While accuracy will be near-identical to the full
    AlphaFold system on many targets, a small fraction have a large drop in accuracy due to the smaller MSA
    and lack of templates. For best reliability, we recommend instead using the [full open source AlphaFold](https://github.com/deepmind/alphafold/),
    or the [AlphaFold Protein Structure Database](https://alphafold.ebi.ac.uk/).

    This Colab has a small drop in average accuracy for multimers compared to local AlphaFold installation,
    for full multimer accuracy it is highly recommended to run [AlphaFold locally](https://github.com/deepmind/alphafold#running-alphafold).
    Moreover, the AlphaFold-Multimer requires searching for MSA for every unique sequence in the complex, hence it is substantially slower.

    Please note that this Colab notebook is provided as an early-access prototype and is not a finished product.
    It is provided for theoretical modelling only and caution should be exercised in its use."

    If you use this function, please cite the [AphaFold paper](https://doi.org/10.1038/s41586-021-03819-2).
    """

    ## Install software
    error = install_packages()
    if error:
        return

    import alphafold as AlphaFold

    ALPHAFOLD_PATH = os.path.abspath(os.path.dirname(AlphaFold.__file__))

    # Import all alphafold programs following installation
    from alphafold.notebooks import notebook_utils
    from alphafold.model import model
    from alphafold.model import config
    from alphafold.model import data

    from alphafold.data import feature_processing
    from alphafold.data import msa_pairing
    from alphafold.data import pipeline
    from alphafold.data import pipeline_multimer

    from alphafold.common import protein

    try:
        from alphafold.relax import utils
    except ModuleNotFoundError as e:
        if "openmm" in str(e):
            logging.error(
                "Dependency openmm v7.5.1 not installed succesfully. Try running 'conda install -c conda-forge openmm=7.5.1' from the command line."
            )
            return

    ## Download model parameters
    # Download parameters if the params directory is empty
    if len(os.listdir(PARAMS_DIR + "params/")) < 2:
        logging.info(
            "Downloading AlphaFold model parameters (requires 4.1 GB of storage). (This might take a few minutes, but only needs to be done during the first 'gget alphafold' call)."
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

        with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process:
            stderr = process.stderr.read().decode("utf-8")
            # Log the standard error if it is not empty
            if stderr:
                sys.stderr.write(stderr)
        # Exit system if the subprocess returned with an error
        if process.wait() != 0:
            return
        else:
            logging.info(f"Parameter download complete.")
    else:
        logging.info("AlphaFold model parameters already downloaded.")

    ## Move stereo_chemical_props.txt from gget bins to Alphafold package so it can be found
    # logging.info("Locate files containing stereochemical properties.")
    if platform.system() == "Windows":
        # The double-quotation marks allow white spaces in the path, but this does not work for Windows
        command = f"""
            mkdir -p {os.path.join(ALPHAFOLD_PATH, 'common/')} \
            && cp -f {STEREO_CHEM_DIR} {os.path.join(ALPHAFOLD_PATH, 'common/')}
            """
    else:
        command = f"""
            mkdir -p '{os.path.join(ALPHAFOLD_PATH, 'common/')}' \
            && cp -f '{STEREO_CHEM_DIR}' '{os.path.join(ALPHAFOLD_PATH, 'common/')}'
            """

    with subprocess.Popen(command, shell=True, stderr=subprocess.PIPE) as process2:
        stderr2 = process2.stderr.read().decode("utf-8")
        # Log the standard error if it is not empty
        if stderr2:
            sys.stderr.write(stderr2)
    # Exit system if the subprocess returned with an error
    if process2.wait() != 0:
        return

    ## Validate input sequence(s)
    logging.info(f"Validating input sequence(s).")

    if type(sequence) == str:
        # Convert string to list
        seqs = [sequence]
    else:
        seqs = sequence

    # If the path to a fasta file was provided instead of a nucleotide sequence,
    # read the file and extract the first sequence
    if "." in sequence:
        if ".txt" in sequence:
            # Read the text file
            titles = []
            seqs = []
            with open(sequence) as text_file:
                for i, line in enumerate(text_file):
                    # Recognize a title line by the '>' character
                    if line[0] == ">":
                        # Append title line to titles list
                        titles.append(line.strip())
                    else:
                        seqs.append(line.strip())

        elif ".fa" in sequence:
            # Read the FASTA
            titles = []
            seqs = []
            with open(sequence) as fasta_file:
                for i, line in enumerate(fasta_file):
                    # Each second line will be a title line
                    if i % 2 == 0:
                        if line[0] != ">":
                            raise ValueError(
                                "Expected FASTA to start with a '>' character. "
                            )
                        else:
                            # Append title line to titles list
                            titles.append(line.strip())
                    else:
                        if line[0] == ">":
                            raise ValueError(
                                "FASTA contains two lines starting with '>' in a row -> missing sequence line. "
                            )
                        # Append sequences line to seqs list
                        else:
                            seqs.append(line.strip())
        else:
            raise ValueError(
                "File format not recognized. gget alphafold only supports '.txt' or '.fa' files. "
            )

    sequences, model_type_to_use = notebook_utils.validate_input(
        input_sequences=seqs,
        min_length=MIN_SINGLE_SEQUENCE_LENGTH,
        max_length=MAX_SINGLE_SEQUENCE_LENGTH,
        max_multimer_length=MAX_MULTIMER_LENGTH,
    )

    ## Find the closest source
    logging.info(f"Finding closest source for reference databases.")

    ex = futures.ThreadPoolExecutor(3)
    fs = [ex.submit(fetch, source) for source in ["", "-europe", "-asia"]]
    source = None
    for f in futures.as_completed(fs):
        source = f.result()
        ex.shutdown()
        break

    DB_ROOT_PATH = f"https://storage.googleapis.com/alphafold-colab{source}/latest/"
    MSA_DATABASES = [
        {
            "db_name": "uniref90",
            "db_path": f"{DB_ROOT_PATH}uniref90_2021_03.fasta",
            "num_streamed_chunks": 59,
            "z_value": 135_301_051,  # The z_value is the number of sequences in a database.
        },
        {
            "db_name": "smallbfd",
            "db_path": f"{DB_ROOT_PATH}bfd-first_non_consensus_sequences.fasta",
            "num_streamed_chunks": 17,
            "z_value": 65_984_053,
        },
        {
            "db_name": "mgnify",
            "db_path": f"{DB_ROOT_PATH}mgy_clusters_2019_05.fasta",
            "num_streamed_chunks": 71,
            "z_value": 304_820_129,
        },
    ]

    # Search UniProt and construct the all_seq features (only for heteromers, not homomers).
    if (
        model_type_to_use == notebook_utils.ModelType.MULTIMER
        and len(set(sequences)) > 1
    ):
        MSA_DATABASES.extend(
            [
                # Swiss-Prot and TrEMBL are concatenated together as UniProt.
                {
                    "db_name": "uniprot",
                    "db_path": f"{DB_ROOT_PATH}uniprot_2021_03.fasta",
                    "num_streamed_chunks": 98,
                    "z_value": 219_174_961 + 565_254,
                },
            ]
        )

    TOTAL_JACKHMMER_CHUNKS = sum([cfg["num_streamed_chunks"] for cfg in MSA_DATABASES])

    ## Search against existing databases
    features_for_chain = {}
    raw_msa_results_for_sequence = {}
    for sequence_index, sequence in enumerate(sequences, start=1):
        logging.info(f"Getting MSA for sequence {sequence_index}.")

        # Temporarily save sequence in fasta file
        fasta_path = f"target_{sequence_index}.fasta"
        with open(fasta_path, "wt") as f:
            f.write(f">query\n{sequence}")

        # Don't do redundant work for multiple copies of the same chain in the multimer.
        if sequence not in raw_msa_results_for_sequence:
            raw_msa_results = get_msa(
                fasta_path=fasta_path,
                msa_databases=MSA_DATABASES,
                total_jackhmmer_chunks=TOTAL_JACKHMMER_CHUNKS,
            )
            raw_msa_results_for_sequence[sequence] = raw_msa_results
        else:
            raw_msa_results = copy.deepcopy(raw_msa_results_for_sequence[sequence])

        # Extract the MSAs from the Stockholm files.
        # NB: deduplication happens later in pipeline.make_msa_features.
        single_chain_msas = []
        uniprot_msa = None
        for db_name, db_results in raw_msa_results.items():
            merged_msa = notebook_utils.merge_chunked_msa(
                results=db_results, max_hits=MAX_HITS.get(db_name)
            )
            if merged_msa.sequences and db_name != "uniprot":
                single_chain_msas.append(merged_msa)
                msa_size = len(set(merged_msa.sequences))
                logging.info(
                    f"{msa_size} unique sequences found in {db_name} for sequence {sequence_index}."
                )
            elif merged_msa.sequences and db_name == "uniprot":
                uniprot_msa = merged_msa

        notebook_utils.show_msa_info(
            single_chain_msas=single_chain_msas, sequence_index=sequence_index
        )

        # Turn the raw data into model features.
        feature_dict = {}
        feature_dict.update(
            pipeline.make_sequence_features(
                sequence=sequence, description="query", num_res=len(sequence)
            )
        )
        feature_dict.update(pipeline.make_msa_features(msas=single_chain_msas))
        # We don't use templates in AlphaFold Colab notebook, add only empty placeholder features.
        feature_dict.update(
            notebook_utils.empty_placeholder_template_features(
                num_templates=0, num_res=len(sequence)
            )
        )

        # Construct the all_seq features only for heteromers, not homomers.
        if (
            model_type_to_use == notebook_utils.ModelType.MULTIMER
            and len(set(sequences)) > 1
        ):
            valid_feats = msa_pairing.MSA_FEATURES + ("msa_species_identifiers",)
            all_seq_features = {
                f"{k}_all_seq": v
                for k, v in pipeline.make_msa_features([uniprot_msa]).items()
                if k in valid_feats
            }
            feature_dict.update(all_seq_features)

        features_for_chain[protein.PDB_CHAIN_IDS[sequence_index - 1]] = feature_dict

    # Do further feature post-processing depending on the model type.
    if model_type_to_use == notebook_utils.ModelType.MONOMER:
        np_example = features_for_chain[protein.PDB_CHAIN_IDS[0]]

    elif model_type_to_use == notebook_utils.ModelType.MULTIMER:
        all_chain_features = {}
        for chain_id, chain_features in features_for_chain.items():
            all_chain_features[chain_id] = pipeline_multimer.convert_monomer_features(
                chain_features, chain_id
            )

        all_chain_features = pipeline_multimer.add_assembly_features(all_chain_features)

        np_example = feature_processing.pair_and_merge(
            all_chain_features=all_chain_features
        )

        # Pad MSA to avoid zero-sized extra_msa.
        np_example = pipeline_multimer.pad_msa(np_example, min_num_seq=512)

    ## Run AlphaFold
    # Run model
    if model_type_to_use == notebook_utils.ModelType.MONOMER:
        model_names = config.MODEL_PRESETS["monomer"] + ("model_2_ptm",)
    elif model_type_to_use == notebook_utils.ModelType.MULTIMER:
        model_names = config.MODEL_PRESETS["multimer"]

    ## Get absolute path to output file and create output directory
    if out is not None:
        os.makedirs(out, exist_ok=True)
        abs_out_path = os.path.abspath(out)

    plddts = {}
    ranking_confidences = {}
    pae_outputs = {}
    unrelaxed_proteins = {}

    with tqdm.notebook.tqdm(
        total=len(model_names) + 1, bar_format=TQDM_BAR_FORMAT
    ) as pbar:
        for model_name in model_names:
            # Set progress bar description
            pbar.set_description(f"Running {model_name}")

            cfg = config.model_config(model_name)
            if model_type_to_use == notebook_utils.ModelType.MONOMER:
                cfg.data.eval.num_ensemble = 1
            elif model_type_to_use == notebook_utils.ModelType.MULTIMER:
                cfg.model.num_ensemble_eval = 1
            params = data.get_model_haiku_params(model_name, PARAMS_DIR)
            model_runner = model.RunModel(cfg, params)
            processed_feature_dict = model_runner.process_features(
                np_example, random_seed=0
            )
            prediction = model_runner.predict(
                processed_feature_dict, random_seed=random.randrange(sys.maxsize)
            )

            mean_plddt = prediction["plddt"].mean()

            if model_type_to_use == notebook_utils.ModelType.MONOMER:
                if "predicted_aligned_error" in prediction:
                    pae_outputs[model_name] = (
                        prediction["predicted_aligned_error"],
                        prediction["max_predicted_aligned_error"],
                    )
                else:
                    # Monomer models are sorted by mean pLDDT. Do not put monomer pTM models here as they
                    # should never get selected.
                    ranking_confidences[model_name] = prediction["ranking_confidence"]
                    plddts[model_name] = prediction["plddt"]
            elif model_type_to_use == notebook_utils.ModelType.MULTIMER:
                # Multimer models are sorted by pTM+ipTM.
                ranking_confidences[model_name] = prediction["ranking_confidence"]
                plddts[model_name] = prediction["plddt"]
                pae_outputs[model_name] = (
                    prediction["predicted_aligned_error"],
                    prediction["max_predicted_aligned_error"],
                )

            # Set the b-factors to the per-residue plddt.
            final_atom_mask = prediction["structure_module"]["final_atom_mask"]
            b_factors = prediction["plddt"][:, None] * final_atom_mask
            unrelaxed_protein = protein.from_prediction(
                processed_feature_dict,
                prediction,
                b_factors=b_factors,
                remove_leading_feature_dimension=(
                    model_type_to_use == notebook_utils.ModelType.MONOMER
                ),
            )
            unrelaxed_proteins[model_name] = unrelaxed_protein

            # Delete unused outputs to save memory.
            del model_runner
            del params
            del prediction
            pbar.update(n=1)

        ## AMBER relax the best model
        # Find the best model according to the mean pLDDT.
        best_model_name = max(
            ranking_confidences.keys(), key=lambda x: ranking_confidences[x]
        )

        if run_relax:
            pbar.set_description(f"AMBER relaxation")

            # Import AlphaFold packages
            try:
                from alphafold.relax import relax
            except ModuleNotFoundError as e:
                if "openmm" in str(e):
                    logging.error(
                        "Dependency openmm v7.5.1 not installed succesfully. Try running 'conda install -c conda-forge openmm=7.5.1' from the command line."
                    )
                    return

            amber_relaxer = relax.AmberRelaxation(
                max_iterations=0,
                tolerance=2.39,
                stiffness=10.0,
                exclude_residues=[],
                max_outer_iterations=3,
                use_gpu=True,
            )
            relaxed_pdb, _, _ = amber_relaxer.process(
                prot=unrelaxed_proteins[best_model_name]
            )
        else:
            logging.warning(
                "Running model without relaxation stage. Use flag [--relax] ('relax=True') to include AMBER relaxation."
            )
            relaxed_pdb = protein.to_pdb(unrelaxed_proteins[best_model_name])

        pbar.update(n=1)

    if out is not None:
        ## Save the prediction
        pred_output_path = os.path.join(abs_out_path, "selected_prediction.pdb")
        with open(pred_output_path, "w") as f:
            f.write(relaxed_pdb)

        ## Save the predicted aligned error
        pae_output_path = os.path.join(abs_out_path, "predicted_aligned_error.json")
        if pae_outputs:
            # Save predicted aligned error in the same format as the AF EMBL DB.
            pae_data = notebook_utils.get_pae_json(pae=pae, max_pae=max_pae.item())
            with open(pae_output_path, "w") as f:
                f.write(pae_data)

    ## Plotting
    # Construct multiclass b-factors to indicate confidence bands
    # 0=very low, 1=low, 2=confident, 3=very high
    banded_b_factors = []
    for plddt in plddts[best_model_name]:
        for idx, (min_val, max_val, _) in enumerate(PLDDT_BANDS):
            if plddt >= min_val and plddt <= max_val:
                banded_b_factors.append(idx)
                break

    banded_b_factors = np.array(banded_b_factors)[:, None] * final_atom_mask
    to_visualize_pdb = utils.overwrite_b_factors(relaxed_pdb, banded_b_factors)

    if plot:
        logging.info("Plotting prediction results.")
        import py3Dmol

        # Show the structure coloured by chain if the multimer model has been used.
        if model_type_to_use == notebook_utils.ModelType.MULTIMER:
            multichain_view = py3Dmol.view(width=800, height=600)
            multichain_view.addModelsAsFrames(to_visualize_pdb)
            multichain_style = {"cartoon": {"colorscheme": "chain"}}
            multichain_view.setStyle({"model": -1}, multichain_style)
            multichain_view.zoomTo()
            multichain_view.show()

        # Color the structure by per-residue pLDDT
        color_map = {i: bands[2] for i, bands in enumerate(PLDDT_BANDS)}
        view = py3Dmol.view(width=800, height=600)
        view.addModelsAsFrames(to_visualize_pdb)
        style = {"cartoon": {"colorscheme": {"prop": "b", "map": color_map}}}
        if show_sidechains:
            style["stick"] = {}
        view.setStyle({"model": -1}, style)
        view.zoomTo()

        grid = GridspecLayout(1, 2)
        output_plt = Output()
        with output_plt:
            view.show()
        grid[0, 0] = out

        output_plt = Output()
        with output_plt:
            plot_plddt_legend().show()
        grid[0, 1] = out

        display.display(grid)

        # Display pLDDT and predicted aligned error (if output by the model).
        if pae_outputs:
            num_plots = 2
        else:
            num_plots = 1

        plt.figure(figsize=[8 * num_plots, 6])
        plt.subplot(1, num_plots, 1)
        plt.plot(plddts[best_model_name])
        plt.title("Predicted LDDT")
        plt.xlabel("Residue")
        plt.ylabel("pLDDT")

        if num_plots == 2:
            plt.subplot(1, 2, 2)
            pae, max_pae = list(pae_outputs.values())[0]
            plt.imshow(pae, vmin=0.0, vmax=max_pae, cmap="Greens_r")
            plt.colorbar(fraction=0.046, pad=0.04)

            # Display lines at chain boundaries.
            best_unrelaxed_prot = unrelaxed_proteins[best_model_name]
            total_num_res = best_unrelaxed_prot.residue_index.shape[-1]
            chain_ids = best_unrelaxed_prot.chain_index
            for chain_boundary in np.nonzero(chain_ids[:-1] - chain_ids[1:]):
                if chain_boundary.size:
                    plt.plot(
                        [0, total_num_res],
                        [chain_boundary, chain_boundary],
                        color="red",
                    )
                    plt.plot(
                        [chain_boundary, chain_boundary],
                        [0, total_num_res],
                        color="red",
                    )

            plt.title("Predicted Aligned Error")
            plt.xlabel("Scored residue")
            plt.ylabel("Aligned residue")

            if out is not None:
                plt.savefig(
                    os.path.join(abs_out_path, "gget_alphafold_results.png"),
                    dpi=300,
                    bbox_inches="tight",
                    transparent=True,
                )

    ## Run clean_up function
    clean_up()
