from silence_tensorflow import silence_tensorflow
silence_tensorflow()

from sklearn.metrics import confusion_matrix, roc_auc_score
from utils.train.visualization import visualize_training
from utils.datasets import get_generators
import matplotlib.pyplot as plt
from seaborn import heatmap
from optparse import OptionParser
import pandas as pd
from tqdm import tqdm
import numpy as np
import json
import os

parser = OptionParser()
parser.add_option('-d', '--dir', dest='dir', default='trained_models/resnet_classifiers/1024/5/barlow_fine_tune_0.5')
# parser.add_option('-n', '--name', dest='name', default='supervised_0.85')
parser.add_option('-v', '--no-visualization', dest='show_training_visualization', default=True, action='store_false')
parser.add_option('-s', '--no-stats', dest='calculate_stats', default=True, action='store_false')
(options, args) = parser.parse_args()

DIR = options.dir
NAME = DIR.split('/')[-1]
TRAINABLE = False if ('barlow' in NAME and 'fine_tune' not in NAME) else True

SHOW_TRAINING_VISUALIZATION = options.show_training_visualization
CALCULATE_STATS = options.calculate_stats

IMAGE_SHAPE = [64, 64, 3]
PROJECTOR_DIMENSIONALITY = 1024
RANDOM_SEED = 42
BATCH_SIZE = 16


if SHOW_TRAINING_VISUALIZATION:
    visualize_training(os.path.join(DIR, NAME + '_history.pickle'))

if CALCULATE_STATS:
    from tensorflow.keras.layers import Input, Dense
    from tensorflow.keras.models import Model
    from tensorflow_addons.metrics import MatthewsCorrelationCoefficient
    from utils.models import resnet20
    import tensorflow as tf

    # Load data
    with open(os.path.join(DIR, 'dataset_config.json'), 'r') as file:
        DATASET_CONFIG = json.load(file)
    datagen_test = get_generators(['test'], IMAGE_SHAPE, BATCH_SIZE, RANDOM_SEED, DATASET_CONFIG)[0]
    datagen_test_minor, datagen_test_major = get_generators(
        ['test'],
        IMAGE_SHAPE, BATCH_SIZE,
        RANDOM_SEED, config=DATASET_CONFIG,
        separate_evaluation_groups=True
    )[0]
    CLASSES = list(datagen_test.class_indices.keys())

    # Load model
    resnet_enc = resnet20.get_network(
        hidden_dim=PROJECTOR_DIMENSIONALITY,
        use_pred=False,
        return_before_head=False,
        input_shape=IMAGE_SHAPE
    )

    inputs = Input(IMAGE_SHAPE)
    x = resnet_enc(inputs)
    resnet_enc.trainable = TRAINABLE
    x = Dense(len(CLASSES), activation='softmax', kernel_initializer='he_normal')(x)
    model = Model(inputs=inputs, outputs=x)
    model.compile(
        optimizer='adam',
        loss='categorical_crossentropy',
        metrics=[
            'acc',
            tf.keras.metrics.TopKCategoricalAccuracy(k=2, name="top_2_accuracy"),
            MatthewsCorrelationCoefficient(num_classes=len(CLASSES), name='MCC')
        ]
    )
    model.load_weights(os.path.join(DIR, NAME + '.h5'))

    # Loss and metrics
    test_loss, test_acc, test_top_2_acc, test_MCC = model.evaluate(datagen_test)
    test_loss_minor, test_acc_minor, test_top_2_acc_minor, test_MCC_minor = model.evaluate(datagen_test_minor)
    test_loss_major, test_acc_major, test_top_2_acc_major, test_MCC_major = model.evaluate(datagen_test_major)

    # Create confusion matrix
    all_labels = []
    all_preds = []

    for idx in tqdm(range(len(datagen_test)), ncols=120):
        X, labels = next(datagen_test)
        preds = model.predict(X)
        all_labels.extend(labels)
        all_preds.extend(preds)

    all_labels = np.array(all_labels)
    all_preds = np.array(all_preds)

    conf_matrix = confusion_matrix(np.argmax(all_labels, axis=-1), np.argmax(all_preds, axis=-1)).astype('int32')
    conf_matrix = pd.DataFrame(conf_matrix, columns=CLASSES, index=CLASSES)
    # confusion_matrix.set_index(CLASSES)

    plt.figure(figsize=(10, 8))
    heatmap(conf_matrix, annot=True)
    plt.ylabel('True Classes')
    plt.xlabel('Predicted Classes')
    plt.show()

    # Calculate AUROC
    micro_auroc = roc_auc_score(all_labels, all_preds, average='micro')
    macro_auroc = roc_auc_score(all_labels, all_preds, average='macro')
    print('Micro AUROC:', round(micro_auroc, 4), 'Macro AUROC:', round(macro_auroc, 4))