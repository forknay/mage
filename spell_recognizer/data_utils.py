from torch.utils.data import DataLoader
from torchvision import datasets, transforms

from config import BATCH_SIZE, DATASET_ROOT


def build_transforms():
    train_transforms = transforms.Compose(
        [
            transforms.Grayscale(num_output_channels=1),
            transforms.RandomRotation(degrees=15),
            transforms.RandomAffine(
                degrees=0,
                translate=(0.05, 0.05),
                scale=(0.9, 1.1),
            ),
            transforms.ToTensor(),
            transforms.Normalize((0.5,), (0.5,)),
        ]
    )

    val_transforms = transforms.Compose(
        [
            transforms.Grayscale(num_output_channels=1),
            transforms.ToTensor(),
            transforms.Normalize((0.5,), (0.5,)),
        ]
    )
    return train_transforms, val_transforms


def load_dataloaders():
    train_transforms, val_transforms = build_transforms()

    train_dataset = datasets.ImageFolder(
        root=str(DATASET_ROOT / "train"), transform=train_transforms
    )
    val_dataset = datasets.ImageFolder(
        root=str(DATASET_ROOT / "val"), transform=val_transforms
    )

    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)

    class_names = train_dataset.classes
    print(f"Detected {len(class_names)} spell classes: {class_names}")

    return train_loader, val_loader, class_names
