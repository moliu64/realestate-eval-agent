"""RealEstate Eval Agent application package."""

import os

# The local embedding model is expected to be cached. Setting these before any
# sentence-transformers / huggingface_hub import keeps startup offline and fast.
# Set HF_HUB_OFFLINE=0 explicitly when the model needs to be downloaded first.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

__version__ = "2.0.0"
