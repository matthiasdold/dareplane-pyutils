import numpy as np

from dareplane_utils.general.ringbuffer import RingBuffer


def test_ringbuffer_init():
    rb = RingBuffer(shape=(10, 3))
    assert rb.buffer.dtype == np.float32
    assert rb.buffer.shape == (10, 3)
    assert (rb.buffer == 0).all()


def test_adding_data_to_ringbuffer():
    rb = RingBuffer(shape=(10, 3))
    rb2 = RingBuffer(shape=(10, 3))

    rb.add_samples(np.ones((5, 3), dtype=np.float32), np.arange(5))

    assert np.all(rb.buffer[:5] == 1)
    assert np.all(rb.buffer[5:] == 0)

    # buffers should not be linked
    assert (rb2.buffer == 0).all()

    # check wrapping around
    rb.add_samples(np.ones((7, 3), dtype=np.float32) * 3, np.arange(7))
    assert np.all(rb.buffer[:2] == 3)
    assert np.all(rb.buffer[5:] == 3)
    assert np.all(rb.buffer[2:5] == 1)


def test_unfolding_ringbuffer():
    rb = RingBuffer(shape=(10, 3))

    rb.add_samples(np.ones((5, 3), dtype=np.float32), np.arange(5))

    d = rb.unfold_buffer()

    assert np.all(d[-5:] == rb.buffer[:5])


def test_multi_dimensional_buffer_adding():

    rb = RingBuffer(shape=(10, 3, 2))

    assert rb.buffer.shape == (10, 3, 2)

    x = np.ones((5, 3, 2), dtype=np.float32)
    rb.add_samples(x, np.arange(5))

    assert np.all(rb.buffer[:5] == 1)

    x = np.ones((7, 3, 2), dtype=np.float32) * 3
    rb.add_samples(x, np.arange(7))

    assert np.all(rb.buffer[:2] == 3)
    assert np.all(rb.buffer[5:] == 3)
    assert np.all(rb.buffer[2:5] == 1)


def test_multi_dimensional_buffer_unfold():

    rb = RingBuffer(shape=(10, 3, 2))

    x = np.ones((15, 3, 2), dtype=np.float32) * np.arange(15).reshape(-1, 1, 1)

    rb.add_samples(x, np.arange(15))

    assert rb.unfold_buffer().shape == (10, 3, 2)
    assert np.all(rb.unfold_buffer()[-1, :, :] == 14)
