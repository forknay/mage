import os
from pathlib import Path

import torch

MODULE_DIR = Path(__file__).resolve().parent
DATASET_ROOT = MODULE_DIR / "dataset_prep"
MODEL_SAVE_PATH = MODULE_DIR / "spell_cnn_model.pth"

BATCH_SIZE = 32
LEARNING_RATE = 0.001
EPOCHS = int(os.getenv("EPOCHS", "15"))
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
