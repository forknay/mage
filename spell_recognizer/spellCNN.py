import torch.nn as nn

IMG_SIZE = 128  # Assuming input images are 128x128 pixels

CHANNELS = [1, 16, 32, 64]  # Number of channels for each convolutional layer
KERNAL_SIZES = [3, 3, 3]  # Kernel sizes for each convolutional layer
POOL_SIZES = [2, 2, 2]  # Pooling sizes for each pooling layer


class SpellCNN(nn.Module):
    def __init__(self, num_classes):
        super(SpellCNN, self).__init__()
        
        # Block 1: Detects basic edges & simple strokes
        # Takes a single-channel input (grayscale image) and outputs 16 feature maps.
        # Applies ReLU activation and 2x2 max pooling to halve spatial dimensions.
        self.block1 = nn.Sequential(
            nn.Conv2d(in_channels=CHANNELS[0], out_channels=CHANNELS[1], kernel_size=KERNAL_SIZES[0], padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=POOL_SIZES[0], stride=POOL_SIZES[0])
        )
        
        # Block 2: Combines strokes into shapes (stars, circles, symbols)
        # Takes 16 feature maps from Block 1 and outputs 32 feature maps, followed by ReLU and MaxPool.
        self.block2 = nn.Sequential(
            nn.Conv2d(in_channels=CHANNELS[1], out_channels=CHANNELS[2], kernel_size=KERNAL_SIZES[1], padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=POOL_SIZES[1], stride=POOL_SIZES[1])
        )
        
        # Block 3: Aggregates shape layouts
        # Takes 32 feature maps and outputs 64 feature maps, followed by ReLU and MaxPool.
        self.block3 = nn.Sequential(
            nn.Conv2d(in_channels=CHANNELS[2], out_channels=CHANNELS[3], kernel_size=KERNAL_SIZES[2], padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=POOL_SIZES[2], stride=POOL_SIZES[2])
        )
        
        # Sequential Fully-Connected Classifier Block
        # Converts spatial features (64 * 16 * 16) down to final class predictions
        self.classifier = nn.Sequential(
            nn.Linear(64 * 16 * 16, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes)
        )

    def forward(self, x):
        # x input shape: (Batch, 1, 128, 128)
        
        # Pass input sequentially through feature extraction blocks
        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)
        
        # Flatten feature maps into 1D vector (Batch, 64 * 16 * 16)
        x = x.view(x.size(0), -1) 
        
        # Pass flattened vector through classifier block
        x = self.classifier(x)
        
        return x

# Example instantiation for 10 distinct spell types
model = SpellCNN(num_classes=10)