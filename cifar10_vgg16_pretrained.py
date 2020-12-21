#####
# dataset: CIFAR-10
# The CIFAR-10 dataset consists of 60000 32x32 colour images in 10 classes, with 6000 images per class.
# training: total 50000 images, divided into 5 batches, each with 10000 images
# (the entire training set contain exactly 5000 images from each class; some batch may contain more images from one
# class than other)
# test: total 10000 images in one batch (1000 randomly-selected images from each class)

# model: VGG16
# ref. paper: VERY DEEP CONVOLUTIONAL NETWORKS FOR LARGE-SCALE IMAGE RECOGNITION

# Notation
# ***: Questions or further information to check are remained
# NOTE: if the code is modified, be aware of the corresponding codes
#####

# Transfer learning from a pretrained network
# ref.
# https://www.tensorflow.org/guide/keras/transfer_learning
# https://www.tensorflow.org/tutorials/images/transfer_learning
# https://blog.exxactcorp.com/discover-difference-deep-learning-training-inference/
# https://towardsdatascience.com/transfer-learning-from-pre-trained-models-f2393f124751
# Idea behind transfer learning:
#   If a model is trained on a large and general enough dataset, it will effectively serve as a generic model
#   of other new, similar problems. This previously trained model is called a pre-trained model.
# General workflow:
#   <Base Model>: Load in the pretrained base model (and pretrained weights)
#       - Take layers from a previously trained model
#       - Freeze them, so as to avoid destroying any of the information they contain during future training rounds
#         which will be used to extract meaningful features from new datasets
#         --> by setting layer.trainable = False:
#             Moves all the layer's weights from trainable (meant to be updated via gradient descent to minimize the
#             loss during training) to non-trainable (aren't meant to be updated during training)
#         *** vs. layer.__call__(training):
#             Controls whether the layer should run its forward pass in inference mode or training mode
#   <Feature extraction>
#   1. Take the output of base model as an input of a classifier model
#       - Run your new dataset through it and record the output of one (or several) layers from
#         the base model
#       - Use that output as input data for a new, smaller model
#   2. Take a base model as a layer of a new model
#       - Stack the classification layers on top, which will learn to turn the old features into predictions on a
#         new dataset. Some of popular approaches to build classifiers are:
#           1) fully connected
#           2) Global avg. pooling
#           3) Linear SVM
#       - Train the new layers on your dataset
#   <(Optional) Fine tuning>: Unfreeze the frozen base model
#       - Unfreeze a few of the top layers or the entire layers of a frozen model
#       - Jointly re-train both the newly-added classifier layers and the last layers of the base model on the new data
#         with a very low learning rate

# Import necessary libraries
import tensorflow as tf
from tensorflow.keras.layers import Conv2D, MaxPooling2D, Dropout, Flatten, Dense
from tensorflow.keras import Input, Model

# Fix the gpu memory issue
config = tf.compat.v1.ConfigProto()
config.gpu_options.per_process_gpu_memory_fraction = 0.3  # NOTE: <=0.3 with GTX 1050 (2GB)
session = tf.compat.v1.Session(config=config)

# Set the value of hyper-parameters
classes = 10
upsampling_size = (3, 3)
learning_rate_ex = 0.001
epochs_ex = 10
fine_tuning = True
learning_rate_tn = 0.0001
epochs_tn = 20

# Results by hyper-parameters
# ==> learning rate: (freeze) 0.001, (unfreeze) 0.0001; Epoch: (freeze) 10, (unfreeze) 10; loss: 0.3986 - accuracy: 0.9064

# Load cifar10 dataset
cifar10 = tf.keras.datasets.cifar10
(x_train, y_train), (x_test, y_test) = cifar10.load_data()

# Preprocess the dataset
x_train, x_test = x_train / 255.0, x_test / 255.0
x_train = x_train.astype("float32")
x_test = x_test.astype("float32")
y_train_onehot = tf.squeeze(tf.one_hot(y_train, classes), axis=1)
y_test_onehot = tf.squeeze(tf.one_hot(y_test, classes), axis=1)

# Feature extraction 2: base model + stacked classification layers at the top
# Instantiate a base model with pre-trained weights (imagenet)
base_model = tf.keras.applications.InceptionV3(
    include_top=False,  # exclude the classifier at the top
    weights='imagenet',  # load weights pre-trained on ImageNet
    input_shape=(96, 96, 3),
    classes=classes
) # 1,1,512

# Stack a new classifier on the base model (fully connected)
input_tensor = Input(shape=(32, 32, 3), dtype='float32', name='input')
upsampling = tf.keras.layers.UpSampling2D(size=upsampling_size, name='upsampling')(input_tensor)
base_layer = base_model(upsampling, training=False, name='base')
flatten = Flatten(name='flatten')(base_layer)
dropout = tf.keras.layers.Dropout(0.2, name='dropout')(flatten)
output_tensor = tf.keras.layers.Dense(classes, activation='softmax', name='output')(dropout)

pretrained2 = tf.keras.Model(input_tensor, output_tensor)
pretrained2.summary()

# Freeze the base model
base_model.trainable = False

# Compile the model
optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate_ex)
pretrained2.compile(loss='categorical_crossentropy',
              optimizer=optimizer,
              metrics=['accuracy'])

# Train the model
history = pretrained2.fit(x_train, y_train_onehot, epochs=epochs_ex,
                          validation_data=(x_test, y_test_onehot))

# Fine tuning
while fine_tuning:
    base_model.trainable = True

    # Fine-tune from this layer onwards (the last conv layer)
    # len(base_model.layers)  # the number of layers in the base model
    fine_tune_at = 16

    # Freeze all the layers before the `fine_tune_at` layer
    for layer in base_model.layers[:fine_tune_at]:
        layer.trainable =  False

    # Compile the model
    optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate_tn)
    pretrained2.compile(loss='categorical_crossentropy',
                        optimizer=optimizer,
                        metrics=['accuracy'])

    # Train the model
    history_fine = pretrained2.fit(x_train, y_train_onehot,
                                   epochs=epochs_tn, initial_epoch=history.epoch[-1],
                                   validation_data=(x_test, y_test_onehot))

    fine_tuning = False

pretrained2.evaluate(x_test, y_test_onehot, verbose=2)

'''
# Initiate a VGG16 architecture
=======
# Freeze the base model
base_model.trainable = False

# Follow 2-2: stack the new layer on the base model
input_tensor = Input(shape=(32, 32, 3), dtype='float32', name='input')
base_layer = base_model(input_tensor, training=False)
avgpool = tf.keras.layers.GlobalAveragePooling2D()(base_layer)
output_tensor = tf.keras.layers.Dense(10)(avgpool)
pretrained2_2 = tf.keras.Model(input_tensor, output_tensor)

# Compile the model
optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate)  # lower learning rate, better performance
pretrained2_2.compile(loss='categorical_crossentropy',  # 'sparse_categorical_crossentropy',
              optimizer=optimizer,
              metrics=['accuracy'])

# Train the model to adjust parameters to minimize the loss
pretrained2_2.fit(x_train, y_train_onehot, batch_size=batch_size, epochs=epochs)

# Predict the model with test set
pretrained2_2.evaluate(x_test, y_test_onehot, verbose=2)

'''# Initiate a VGG16 architecture
>>>>>>> bdebe3b... updates
input_tensor = Input(shape=(32, 32, 3), dtype='float32', name='input')
# Rescale image (up-sampling) for better performance
# NOTE: change the next layer's input
# upsampling = tf.keras.layers.UpSampling2D(size=upsampling_size, name='upsampling')(input_tensor)

# block 1
conv1_1 = Conv2D(64, 3, activation='relu', padding='same', name='conv1-1')(input_tensor)
conv1_2 = Conv2D(64, 3, activation='relu', padding='same', name='conv1-2')(conv1_1)
maxpool1 = MaxPooling2D(2, padding='same', name='maxpool1')(conv1_2)  # down-sampling # 16,16,64
# block 2
conv2_1 = Conv2D(128, 3, activation='relu', padding='same', name='conv2-1')(maxpool1)
conv2_2 = Conv2D(128, 3, activation='relu', padding='same', name='conv2-2')(conv2_1)
maxpool2 = MaxPooling2D(2, padding='same', name='maxpool2')(conv2_2)  # 8,8,128
# block 3
conv3_1 = Conv2D(256, 3, activation='relu', padding='same', name='conv3-1')(maxpool2)
conv3_2 = Conv2D(256, 3, activation='relu', padding='same', name='conv3-2')(conv3_1)
conv3_3 = Conv2D(256, 3, activation='relu', padding='same', name='conv3-3')(conv3_2)
maxpool3 = MaxPooling2D(2, padding='same', name='maxpool3')(conv3_3)  # 4,4,256
# block 4
conv4_1 = Conv2D(512, 3, activation='relu', padding='same', name='conv4-1')(maxpool3)
conv4_2 = Conv2D(512, 3, activation='relu', padding='same', name='conv4-2')(conv4_1)
conv4_3 = Conv2D(512, 3, activation='relu', padding='same', name='conv4-3')(conv4_2)
maxpool4 = MaxPooling2D(2, padding='same', name='maxpool4')(conv4_3)  # 2,2,512
# block 5
conv5_1 = Conv2D(512, 3, activation='relu', padding='same', name='conv5-1')(maxpool4)
conv5_2 = Conv2D(512, 3, activation='relu', padding='same', name='conv5-2')(conv5_1)
conv5_3 = Conv2D(512, 3, activation='relu', padding='same', name='conv5-3')(conv5_2)
maxpool5 = MaxPooling2D(2, padding='same', name='maxpool5')(conv5_3)  # 1,1,512

# Fully connected (FC)
flatten = Flatten(name='flatten')(maxpool5)
# fc1 = Dense(4096, activation='relu', name='fc1')(flatten) # unnecessary due to the final dimension size after block 5
# fc2 = Dense(2048, activation='relu', name='fc2')(fc1)
fc3 = Dense(256, activation='relu', name='fc3')(flatten)  # NOTE: check input
output_tensor = Dense(10, activation='softmax', name='output')(fc3)

# Create a model
vgg16 = Model(input_tensor, output_tensor, name='vgg16')
<<<<<<< HEAD
vgg16.summary()  # plot the model architecture with the number of parameters (complexity)
'''
=======
vgg16.summary()  # plot the model architecture with the number of parameters (complexity)'''


>>>>>>> bdebe3b... updates
