import torch
from spellCNN import SpellCNN

# 1. Instantiate model and load trained weights
num_classes = 4  # Replace with your actual number of spell classes
model = SpellCNN(num_classes=num_classes)
model.load_state_dict(torch.load("spell_cnn_model.pth"))

# Set model to evaluation mode (disables dropout, fixes batchnorm if present)
model.eval()

# 2. Create a dummy input matching the expected shape: (Batch Size, Channels, Height, Width)
# Here: 1 image, 1 grayscale channel, 128x128 resolution
dummy_input = torch.randn(1, 1, 128, 128)

# 3. Define output path
onnx_file_path = "spell_cnn.onnx"

# 4. Export to ONNX
torch.onnx.export(
    model,                      # Model being run
    dummy_input,                # Model input (or a tuple for multiple inputs)
    onnx_file_path,             # File destination
    export_params=True,         # Store the trained parameter weights inside the model file
    opset_version=14,           # ONNX version (14+ recommended for modern compatibility)
    do_constant_folding=True,   # Optimizes constants during export
    input_names=['input'],      # Input tensor name in ONNX
    output_names=['output'],    # Output tensor name in ONNX
    dynamic_axes={              # Allows dynamic batch sizes during runtime (e.g., batch size 1 or 16)
        'input': {0: 'batch_size'},
        'output': {0: 'batch_size'}
    }
)

print(f"Model successfully saved as {onnx_file_path}!")