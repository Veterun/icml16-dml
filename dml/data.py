"""Methods and routines to manipulate timbre data."""

import glob
import numpy as np
import os
import pandas as pd
import pescador
import random

import dml.utils as utils


def parse_filename(fname, sep='_'):
    """Parse a VSL filename into its constituent components.

    Parameters
    ----------
    fname : str
        Filename to parse

    Returns
    -------
    icode, note_number, fcode : str
        Instrument code, note number, and file-ID, respectively.
    """
    i, n, f = utils.filebase(fname).split(sep)[:3]
    return i, int(n), f


def index_directory(base_dir, sep='_'):
    """Index a directory of VSL feature files as a pandas DataFrame.

    Parameters
    ----------
    base_dir : str
        Directory to index.

    Returns
    -------
    dset : pd.DataFrame
        Data frame of features.
    """
    records = []
    index = []
    for f in glob.glob(os.path.join(base_dir, "*.npz")):
        icode, nnum, fcode = parse_filename(f, sep)
        records += [dict(features=f, instrument=icode,
                         note_number=nnum, fcode=fcode,
                         inst_note="{}_{}".format(icode, nnum))]
        index += [sep.join([str(x) for x in parse_filename(f, sep)])]

    return pd.DataFrame.from_records(records, index=index)


def split_dataset(dframe, ratio=0.5):
    """Split dataset into two disjoint sets.

    Parameters
    ----------
    dframe : pd.DataFrame
        Dataset to split.

    Returns
    -------
    set1, set2 : pd.DataFrames
        Partitioned sets.
    """
    index = np.array(dframe.index.tolist())
    np.random.shuffle(index)

    tr_size = int(ratio * len(index))
    tr_index = index[:tr_size]
    te_index = index[tr_size:]

    return dframe.loc[tr_index], dframe.loc[te_index]


def instrument_neighbors(dframe):
    """Create lists of instrument neighbors.

    Parameters
    ----------
    dframe : pd.DataFrame
        Dataframe of the sample index.

    Returns
    -------
    neighbors : dict of lists
        Map of instrument keys to lists of related indexes.
    """
    return {i: dframe[dframe.instrument == i].index.tolist()
            for i in dframe.instrument.unique()}


def pitch_neighbors(dframe, pitch_delta=0):
    """Create lists of instrument/pitch neighbors.

    Parameters
    ----------
    dframe : pd.DataFrame
        Dataframe of the sample index.

    pitch_delta : int, default=0
        Number of pitch values (plus/minus) for forming neighborhoods.

    Returns
    -------
    neighbors : dict of lists
        Map of note numbers to lists of related indexes.
    """
    return {nn: dframe[dframe.note_number == nn].index.tolist()
            for nn in dframe.note_number.unique()}

    # TODO: Keep this around in case pitch-only neighborhoods seems like a
    # good idea. Currently, seems like this neighborhood might be too big?
    # ------------------
    # neighbors = dict()
    # for nn in dframe.note_number.unique():
    #     key = "{}".format(nn)
    #     nidx = np.abs(dframe.note_number - nn) <= pitch_delta
    #     neighbors[key] = dframe[nidx].index.tolist()
    # return neighbors


def instrument_pitch_neighbors(dframe, pitch_delta=0, min_population=0):
    """Create lists of instrument/pitch neighbors.

    Parameters
    ----------
    dframe : pd.DataFrame
        Dataframe of the sample index.

    pitch_delta : int, default=0
        Number of pitch values (plus/minus) for forming neighborhoods.

    Returns
    -------
    neighbors : dict of lists
        Map of instrument/pitch keys to lists of related indexes.
    """
    neighbors = dict()
    for i in dframe.instrument.unique():
        for nn in dframe.note_number.unique():
            key = "{}_{}".format(i, nn)
            nidx = np.abs(dframe.note_number - nn) <= pitch_delta
            iidx = (dframe.instrument == i)
            c = (nidx & iidx).sum()
            if c > min_population:
                neighbors[key] = dframe[nidx & iidx].index.tolist()
    return neighbors


def population_filter(neighbors, min_population):
    """Drop key-index pairs with insufficient populations.

    Parameters
    ----------
    neighbors : dict
        Key-index mappings.

    min_population : int
        Minimum number of items to keep, inclusive.

    Returns
    -------
    filt_neighbors : dict
        Population-filtered key-index mappings.
    """
    nbs = {}
    keys = list(neighbors.keys())
    for k in keys:
        if len(neighbors[k]) >= min_population:
            nbs[k] = neighbors[k]
    return nbs


def slice_cqt(row, window_length):
    """Generate slices of CQT observations.

    Parameters
    ----------
    row : pd.Series
        Row from a features dataframe.

    window_length : int
        Length of the CQT slice in time.

    Yields
    ------
    x_obs : np.ndarray
        Slice of cqt data.

    meta : dict
        Metadata corresponding to the observation.
    """
    try:
        data = np.load(row.features)['cqt']
    except IOError as derp:
        print("Failed reading row: {}\n\n{}".format(row.to_dict(), derp))
        raise derp

    num_obs = data.shape[1]
    # Break the remainder out into a subfunction for reuse with embedding
    # sampling.
    idx = np.random.permutation(num_obs) if num_obs > 0 else None
    if idx is None:
        raise ValueError(
            "Misshapen CQT ({}) - {}".format(data.shape, row.to_dict()))
    np.random.shuffle(idx)
    counter = 0
    meta = dict(instrument=row.instrument, note_number=row.note_number,
                fcode=row.fcode)

    while num_obs > 0:
        n = idx[counter]
        obs = utils.padded_slice_ndarray(data, n, length=window_length, axis=1)
        obs = obs[np.newaxis, ...]
        meta['idx'] = n
        yield obs, meta
        counter += 1
        if counter >= len(idx):
            np.random.shuffle(idx)
            counter = 0


def slice_cqt_weighted(row, window_length):
    """Generate slices of CQT observations.

    Parameters
    ----------
    row : pd.Series
        Row from a features dataframe.

    window_length : int
        Length of the CQT slice in time.

    Yields
    ------
    x_obs : np.ndarray
        Slice of cqt data.

    meta : dict
        Metadata corresponding to the observation.
    """
    try:
        data = np.load(row.features)['cqt']
    except IOError as derp:
        print("Failed reading row: {}\n\n{}".format(row.to_dict(), derp))
        raise derp

    # Create an index likelihood as a function of amplitude
    weights = data.squeeze().sum(axis=-1)
    weights /= weights.sum()
    meta = dict(instrument=row.instrument, note_number=row.note_number,
                fcode=row.fcode)

    while True:
        n = np.random.multinomial(1, weights).argmax()
        obs = utils.padded_slice_ndarray(data, n, length=window_length, axis=1)
        obs = obs[np.newaxis, ...]
        meta['idx'] = n
        yield obs, meta


def neighbor_stream(neighbors, dataset, slice_func,
                    working_size=10, lam=25, with_meta=False,
                    **kwargs):
    """Produce a sample stream of positive and negative examples.

    Parameters
    ----------
    neighbors : dict of lists
        Map of neighborhood keys (names) to lists of related indexes.

    dataset : pd.DataFrame
        Dataset from which to sample.

    slice_func : callable
        Method for slicing observations from a npz archive.

    working_size : int, default=10
        Number of sample sources to keep alive.

    lam : number, default=25
        Sample refresh-rate parameter.

    with_meta : bool, default=False
        If True, yields a tuple of (X, Y) data.

    kwargs : dict
        Keyword arguments to pass through to the slicing function.

    Yields
    ------
    x_in, x_same, x_diff : np.ndarrays
        Tensors corresponding to the base observation, a similar datapoint,
        and a different one.

    y_in, y_same, y_diff : dicts
        Metadata corresponding to the samples 'x' data.
    """
    streams = dict()
    for key, indexes in neighbors.items():
        seed_pool = [pescador.Streamer(slice_func, dataset.loc[idx], **kwargs)
                     for idx in indexes]
        streams[key] = pescador.mux(seed_pool, n_samples=None,
                                    k=working_size, lam=lam)
    while True:
        keys = list(streams.keys())
        idx = random.choice(keys)
        x_in, y_in = next(streams[idx])
        x_same, y_same = next(streams[idx])
        keys.remove(idx)
        idx = random.choice(keys)
        x_diff, y_diff = next(streams[idx])
        result = (dict(x_in=x_in, x_same=x_same, x_diff=x_diff),
                  dict(y_in=y_in, y_same=y_same, y_diff=y_diff))
        yield result if with_meta else result[0]


NEIGHBORS = {
    "instrument": instrument_neighbors,
    "pitch": pitch_neighbors,
    "instrument-pitch": instrument_pitch_neighbors
}


def class_stream(neighbors, dataset, working_size=20, lam=5, with_meta=False):
    streams = dict()
    for key, indexes in neighbors.items():
        seed_pool = [pescador.Streamer(slice_embedding, dataset.loc[idx])
                     for idx in indexes]
        streams[key] = pescador.mux(seed_pool, n_samples=None,
                                    k=working_size, lam=lam)
    while True:
        keys = list(streams.keys())
        idx = random.choice(keys)
        x_in, meta = next(streams[idx])

        result = (dict(x_in=x_in, y=np.array([idx])),
                  meta)
        yield result if with_meta else result[0]


SAMPLERS = {
    'uniform': slice_cqt,
    'weighted': slice_cqt_weighted
}


def create_stream(dataset, neighbor_mode, batch_size, window_length,
                  sample_mode='uniform', working_size=25, lam=25,
                  pitch_delta=0):
    """Create a data stream.

    Parameters
    ----------
    dataset : pd.DataFrame
        Dataset to sample from.

    neighbor_mode : str
        One of ['instrument', 'pitch', 'instrument-pitch'].

    batch_size : int
        Number of datapoints in each batch.

    window_length : int
        Number of time frames per observation.

    working_size : int, default=25
        Number of samples to keep alive per neighborhood.

    lam : number, default=25
        Poisson parameter for refreshing a sample substream.

    pitch_delta : int, default=0
        Semitone distance for pitch neighbors.

    Yields
    ------
    batch : dict
        Input names mapped to np.ndarrays.
    """
    nb_kwargs = dict()
    if neighbor_mode == 'instrument-pitch':
        nb_kwargs['pitch_delta'] = pitch_delta

    neighbors = NEIGHBORS.get(neighbor_mode)(dataset, **nb_kwargs)
    stream = neighbor_stream(
        neighbors, dataset, slice_func=SAMPLERS.get(sample_mode),
        window_length=window_length,
        lam=lam, working_size=working_size)

    return pescador.buffer_batch(stream, buffer_size=batch_size)


def awgn(stream, loc, scale):
    for data in stream:
        for k in data:
            data[k] += np.random.normal(loc, scale, data[k].shape)

        yield data


def slice_embedding(row, n_length=1):
    """Generate slices of CQT observations.

    Parameters
    ----------
    row : pd.Series
        Row from a features dataframe.

    Yields
    ------
    z_obs : np.ndarray
        Embedding coordinate.

    meta : dict
        Metadata corresponding to the observation.
    """
    try:
        data = np.load(row.prediction)['z_out']
    except IOError as derp:
        print("Failed reading row: {}\n\n{}".format(row.to_dict(), derp))
        raise derp

    num_obs = data.shape[0] + 1 - n_length
    # Break the remainder out into a subfunction for reuse with embedding
    # sampling.
    idx = np.random.permutation(num_obs) if num_obs > 0 else None
    if idx is None:
        raise ValueError(
            "Misshapen CQT ({}) - {}".format(data.shape, row.to_dict()))
    np.random.shuffle(idx)
    counter = 0
    meta = dict(instrument=row.instrument, note_number=row.note_number,
                fcode=row.fcode)

    while num_obs > 0:
        n = idx[counter]
        obs = data[n:n + n_length]
        meta['idx'] = n
        yield obs, meta
        counter += 1
        if counter >= len(idx):
            np.random.shuffle(idx)
            counter = 0


def create_embedding_stream(dataset, working_size=100, lam=5, **kwargs):
    seed_pool = [pescador.Streamer(slice_embedding, row, **kwargs)
                 for idx, row in dataset.iterrows()]
    return pescador.mux(seed_pool, n_samples=None,
                        k=working_size, lam=lam)


def sample_embeddings(dataset, num_points):
    """Sample a collection of embedding points from a dataset.

    Parameters
    ----------
    dataset : pd.DataFrame
        DataFrame of embeddings.

    num_points : int
        Number of datapoints to sample.

    Returns
    -------
    data : np.ndarray, shape=(num_points, 3)
        Observations.

    labels : pd.DataFrame, len=num_points
        Sample labels.
    """
    # Eeek! Magic number.
    data = np.zeros([num_points, 3])
    labels = list()

    stream = create_embedding_stream(
        dataset, n_length=1, working_size=100, lam=5)

    for n in range(num_points):
        coords, meta = next(stream)
        data[n, ...] = coords
        labels.append(meta)

    return data, pd.DataFrame.from_records(labels, index=range(num_points))
