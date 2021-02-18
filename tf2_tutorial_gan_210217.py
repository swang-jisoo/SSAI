#####
# Dataset: mnist handwritten digits

# Model: GAN
# ref.
# - 참고 논문: GAN 1
# - https://www.tensorflow.org/tutorials/generative/dcgan
#####

# Import necessary libraries
import tensorflow as tf
import glob
import imageio
import matplotlib.pyplot as plt
import numpy as np
import os
import PIL
from tensorflow.keras import layers
import time
from IPython import display
import tf2_tutorial_gan_embed as embed


# Parameters
BUFFER_SIZE = 60000
BATCH_SIZE = 256
EPOCHS = 50
noise_dim = 100
num_examples_to_generate = 16
learning_rate = 1e-4


# Load the dataset
(train_images, train_labels), (_, _) = tf.keras.datasets.mnist.load_data()
# Prepare the dataset
train_images = train_images.reshape(train_images.shape[0], 28, 28, 1).astype('float32')
# Normalize the images to [-1, 1] to match Generater (tanh) output
train_images = (train_images - 127.5) / 127.5
# Batch and shuffle the data
train_dataset = tf.data.Dataset.from_tensor_slices(train_images).shuffle(BUFFER_SIZE).batch(BATCH_SIZE)


# Create the Generator
def make_generator_model():
    model = tf.keras.Sequential()

    # *** Better using a FC layer (less parameter, computation) rather than initializing noise = 7*7*256
    model.add(layers.Dense(7 * 7 * 256, use_bias=False, input_shape=(noise_dim,)))  # (, 7*7*256=12544)
    model.add(layers.BatchNormalization())
    # traditional ReLU: output is either positive (same as original positive) or zero (originally negative)
    # Since this makes the model a lot sparser, the training process tends to be impacted only by the features
    # in your dataset that actually contribute to the model’s decision power.
    # When the optimizer becomes less fierce when training progresses, some weights may be just too negative –
    # and they can no longer ‘escape’ from the zero-ReLU-activation.
    # LeakyReLU: output is either positive (same as original positive) or small negative (0.1*original negative)
    model.add(layers.LeakyReLU())

    model.add(layers.Reshape((7, 7, 256)))  # (, 7, 7, 256)
    assert model.output_shape == (None, 7, 7, 256)  # Note: None is the batch size

    # In Conv2D, padding = same means to generate the output with a size of (input size / stride) approximately
    # Thus, with stride = 1, padding = same results the size of input & output to be same
    # In contrast to Conv2D, in Conv2DTranspose, padding
    # Conv2D output: Input W - Kernal W + 2(Padding) + 1
    # With stride = 1, padding = same means the size of input & output are same
    # With stride > 1, padding = (Kernal W - 1) / 2, resulting the size of output = input size / stride approximately
    # e.g.) Conv2D(128, (5,5), strides=(1,1))(tf.random.normal([256,7,7,256])) --> (256, 3, 3, 128)
    # Conv2DTranspose output: Input W - 1 + Kernal W - 2(Padding)  # contrast to Conv2D
    # e.g.) Conv2DTranspose(128, (5,5), strides=(1,1))(tf.random.normal([256,7,7,256])) --> (256, 11, 11, 128)
    model.add(layers.Conv2DTranspose(128, (5, 5), strides=(1, 1), padding='same', use_bias=False))  # (, 7, 7, 128)
    assert model.output_shape == (None, 7, 7, 128)
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())

    model.add(layers.Conv2DTranspose(64, (5, 5), strides=(2, 2), padding='same', use_bias=False))  # (, 14, 14, 64)
    assert model.output_shape == (None, 14, 14, 64)
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())

    # tanh activation: output is between (-1,1)
    model.add(layers.Conv2DTranspose(1, (5, 5), strides=(2, 2), padding='same', use_bias=False,
                                     activation='tanh'))  # (, 28, 28, 1)
    assert model.output_shape == (None, 28, 28, 1)
    # output: a fake image with the desired size of 28*28*1

    return model


'''
# Use the (as yet untrained) generator to create an image.
generator = make_generator_model()

noise = tf.random.normal([1, 100])
generated_image = generator(noise, training=False)
plt.imshow(generated_image[0, :, :, 0], cmap='gray')
'''


# Create the Discriminator
def make_discriminator_model():
    model = tf.keras.Sequential()
    model.add(layers.Conv2D(64, (5, 5), strides=(2, 2), padding='same', input_shape=[28, 28, 1]))  # (, 14, 14, 64)
    model.add(layers.LeakyReLU())
    model.add(layers.Dropout(0.3))

    model.add(layers.Conv2D(128, (5, 5), strides=(2, 2), padding='same'))  # (, 7, 7, 128)
    model.add(layers.LeakyReLU())
    model.add(layers.Dropout(0.3))

    model.add(layers.Flatten())  # (, 7*7*128 = 6272)
    model.add(layers.Dense(1))  # binary
    # output: positive values for real images, and negative values for fake images

    return model


'''
# Use the (as yet untrained) discriminator to classify the generated images as real or fake
discriminator = make_discriminator_model()
decision = discriminator(generated_image)
print(decision)  # tf.Tensor([[-0.00173489]], shape=(1, 1), dtype=float32)
'''


# Define the loss and optimizers
# This method returns a helper function to compute cross entropy loss
cross_entropy = tf.keras.losses.BinaryCrossentropy(from_logits=True)


# This method quantifies how well the discriminator is able to distinguish real images from fakes.
# It compares the discriminator's predictions on real images to an array of 1s,
# and the discriminator's predictions on fake (generated) images to an array of 0s.
def discriminator_loss(real_output, fake_output):
    real_loss = cross_entropy(tf.ones_like(real_output), real_output)
    fake_loss = cross_entropy(tf.zeros_like(fake_output), fake_output)
    total_loss = real_loss + fake_loss
    return total_loss


# The generator's loss quantifies how well it was able to trick the discriminator.
# Intuitively, if the generator is performing well, the discriminator will classify the fake images as real (or 1).
# Here, we will compare the discriminators decisions on the generated images to an array of 1s.
def generator_loss(fake_output):
    return cross_entropy(tf.ones_like(fake_output), fake_output)


# The discriminator and the generator optimizers are different since we will train two networks separately.
generator_optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate)
discriminator_optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate)


# Save checkpoints and restore models, which can be helpful in case a long running training task is interrupted
generator = make_generator_model()
discriminator = make_discriminator_model()

checkpoint_dir = './training_checkpoints'
checkpoint_prefix = os.path.join(checkpoint_dir, "ckpt")
checkpoint = tf.train.Checkpoint(generator_optimizer=generator_optimizer,
                                 discriminator_optimizer=discriminator_optimizer,
                                 generator=generator,
                                 discriminator=discriminator)


# Define the training loop
# We will reuse this seed overtime (so it's easier) to visualize progress in the animated GIF
seed = tf.random.normal([num_examples_to_generate, noise_dim])


# The training loop begins with generator receiving a random seed as input. That seed is used to produce an image.
# The discriminator is then used to classify real images (drawn from the training set)
# and fakes images (produced by the generator). The loss is calculated for each of these models,
# and the gradients are used to update the generator and discriminator.
# Notice the use of `tf.function`
# This annotation causes the function to be "compiled".
# ref. https://www.tensorflow.org/guide/function?hl=ko
@tf.function
def train_step(images):
    # **** noise size, BATCH
    noise = tf.random.normal([BATCH_SIZE, noise_dim])

    with tf.GradientTape() as gen_tape, tf.GradientTape() as disc_tape:
        generated_images = generator(noise, training=True)

        real_output = discriminator(images, training=True)
        fake_output = discriminator(generated_images, training=True)

        gen_loss = generator_loss(fake_output)
        disc_loss = discriminator_loss(real_output, fake_output)

    gradients_of_generator = gen_tape.gradient(gen_loss, generator.trainable_variables)
    gradients_of_discriminator = disc_tape.gradient(disc_loss, discriminator.trainable_variables)

    generator_optimizer.apply_gradients(zip(gradients_of_generator, generator.trainable_variables))
    discriminator_optimizer.apply_gradients(zip(gradients_of_discriminator, discriminator.trainable_variables))

    return gen_loss, disc_loss


def train(dataset, epochs):
    for epoch in range(epochs):
        start = time.time()
        gen_losses, disc_losses = [], []

        for image_batch in dataset:
            gen_loss, disc_loss = train_step(image_batch)
            gen_losses.append(gen_loss)
            disc_losses.append(disc_loss)

        # Produce images for the GIF as we go
        display.clear_output(wait=True)
        generate_and_save_images(generator, epoch + 1, seed)

        # Save the model every 15 epochs
        if (epoch + 1) % 15 == 0:
            checkpoint.save(file_prefix=checkpoint_prefix)

        print('Time for epoch {} is {} sec'.format(epoch + 1, time.time() - start))
        gen_loss_avg = sum(gen_losses) / len(gen_losses)
        disc_loss_avg = sum(disc_losses) / len(disc_losses)
        print('Generator Loss: {:.4f} & Discriminator Loss: {:.4f}'.format(gen_loss_avg, disc_loss_avg))

    # Generate after the final epoch
    display.clear_output(wait=True)
    generate_and_save_images(generator, epochs, seed)


# Generate and save images
def generate_and_save_images(model, epoch, test_input):
    # Notice `training` is set to False.
    # This is so all layers run in inference mode (batchnorm).
    predictions = model(test_input, training=False)

    fig = plt.figure(figsize=(4, 4))

    for i in range(predictions.shape[0]):
        plt.subplot(4, 4, i + 1)
        plt.imshow(predictions[i, :, :, 0] * 127.5 + 127.5, cmap='gray')
        plt.axis('off')

    plt.savefig('image_at_epoch_{:04d}.png'.format(epoch))
    # plt.show()


# Train the model
# Note, training GANs can be tricky.
# It's important that the generator and discriminator do not overpower each other (e.g., that they train at a similar rate).
train(train_dataset, EPOCHS)
# Restore the latest checkpoint
checkpoint.restore(tf.train.latest_checkpoint(checkpoint_dir))


# Create a GIF
# Display a single image using the epoch number
def display_image(epoch_no):
    return PIL.Image.open('image_at_epoch_{:04d}.png'.format(epoch_no))


# display_image(EPOCHS)

anim_file = 'dcgan.gif'

with imageio.get_writer(anim_file, mode='I') as writer:
    filenames = glob.glob('image*.png')
    filenames = sorted(filenames)
    for filename in filenames:
        image = imageio.imread(filename)
        writer.append_data(image)
    image = imageio.imread(filename)
    writer.append_data(image)

embed.embed_file(anim_file)
