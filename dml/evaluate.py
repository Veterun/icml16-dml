import json
import os
import time

from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import precision_recall_curve
from sklearn.metrics import average_precision_score
from sklearn.preprocessing import label_binarize
from sklearn.metrics import confusion_matrix

import dml.data as D


def knn_classify(train, valid, test,
                 num_neighbors=[1, 5, 9, 15, 21, 35, 51, 75],
                 num_train=25000, num_valid=2500, num_test=25000):
    x_train, y_train = D.sample_embeddings(train, num_train)
    x_valid, y_valid = D.sample_embeddings(valid, num_valid)
    x_test, y_test = D.sample_embeddings(test, num_test)

    col_name = 'instrument'
    y_train = y_train[col_name]
    y_valid = y_valid[col_name]
    y_test = y_test[col_name]

    best_knn = None
    best_score = -1
    for k in num_neighbors:
        knn = KNeighborsClassifier(n_neighbors=k)
        knn.fit(x_train, y_train)
        score = knn.score(x_valid, y_valid)
        if score > best_score:
            best_knn = knn
            best_score = score
            print("[{0}] New Best @ k={1}: {2:.4}"
                  "".format(time.asctime(), k, best_score))

    proba_test = knn.predict_proba(x_test)
    Y_test = label_binarize(y_test, classes=best_knn.classes_)

    # Compute micro-average ROC curve and ROC area
    precision_micro, recall_micro, _ = precision_recall_curve(
        Y_test.ravel(), proba_test.ravel())

    average_precision_micro = average_precision_score(
        Y_test, proba_test, average="micro")
    conf_mat = confusion_matrix(y_test, best_knn.predict(x_test))
    return dict(
        average_precision_micro=average_precision_micro,
        precision_micro=precision_micro.tolist(),
        recall_micro=recall_micro.tolist(),
        confusion_matrix=conf_mat.tolist(),
        class_labels=best_knn.classes_.tolist(),
        train_score=best_knn.score(x_train, y_train),
        valid_score=best_knn.score(x_valid, y_valid),
        test_score=best_knn.score(x_test, y_test))
