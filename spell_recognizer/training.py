from data_utils import load_dataloaders
from model_utils import build_model, save_model, train_model


def main():
    train_loader, val_loader, class_names = load_dataloaders()
    num_classes = len(class_names)

    model = build_model(num_classes)
    model = train_model(model, train_loader, val_loader)
    save_model(model)


if __name__ == "__main__":
    main()
