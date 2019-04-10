import dask.array as da


def _tiledb_to_chunks(tiledb_array):
    """
    tiledb tiling:
        - http://docs.dask.org/en/latest/array-chunks.html
    dask chunks:
        - http://docs.dask.org/en/latest/array-chunks.html

    TileDB tile extents correspond to form 2 of the dask
    chunk specifier specification:

        "A uniform chunk shape like (1000, 2000, 3000),
         meaning chunks of size 1000 in the first axis,
         2000 in the second axis, and 3000 in the third"

    :param array: tiledb.Array
    :return: list
    """
    schema = tiledb_array.schema
    return list(schema.domain.dim(i).tile for i in range(schema.ndim))


def from_tiledb(uri, attribute=None, chunks=None,
                storage_options=None, **kwargs):
    """Load array from the TileDB storage database

    See https://docs.tiledb.io for more information.

    Parameters
    ----------
    uri: TileDB array or str
        Location to save the data
    attribute: str or None
        Attribute selection (single-attribute view on multi-attribute array)

    Examples
    --------

    >> # create a tiledb array
    >> import tiledb, numpy as np, tempfile
    >> uri = tempfile.NamedTemporaryFile().name
    >> tiledb.from_numpy(uri, np.arange(0,9).reshape(3,3))
    <tiledb.libtiledb.DenseArray object at 0x...>
    >> # read back the array
    >> import dask.array as da
    >> tdb_ar = da.from_tiledb(uri)
    >> tdb_ar.shape
    (3, 3)
    >> tdb_ar.mean().compute()
    4.0
    """
    import tiledb
    tiledb_config = storage_options or dict()
    key = tiledb_config.pop('key', None)

    if isinstance(uri, tiledb.Array):
        tdb = uri
    else:
        tdb = tiledb.open(uri, attr=attribute, config=tiledb_config, key=key)

    if tdb.schema.sparse:
        raise ValueError("Sparse TileDB arrays are not supported")

    if not attribute:
        if tdb.schema.nattr > 1:
            raise TypeError("keyword 'attribute' must be provided"
                            "when loading a multi-attribute TileDB array")
        else:
            attribute = tdb.schema.attr(0).name

    if tdb.iswritable:
        raise ValueError("TileDB array must be open for reading")

    chunks = chunks or _tiledb_to_chunks(tdb)

    assert(len(chunks) == tdb.schema.ndim)

    return da.from_array(tdb, chunks, name='tiledb-%s' % uri)


def to_tiledb(darray, uri, compute=True, return_stored=False,
              storage_options=None, **kwargs):
    """Save 'array' using the TileDB storage manager, to any TileDB-supported URI,
    including local disk, S3, or HDFS.

    See https://docs.tiledb.io for more information about TileDB.

    Parameters
    ----------

    darray: dask.array
        A dask array to write.
    uri:
        Any supported TileDB storage location.
    storage_options:
        Dict containing any configuration options for the TileDB backend.
        see https://docs.tiledb.io/en/stable/tutorials/config.html
    compute, return_stored: see ``store()``
    :return:
        None

    Examples
    --------

    >> import dask.array as da, tempfile
    >> uri = tempfile.NamedTemporaryFile().name
    >> data = da.random.random(5,5)
    >> da.to_tiledb(data, uri)
    >> import tiledb
    >> tdb_ar = tiledb.open(uri)
    >> all(tdb_ar == data)
    True
    """
    import tiledb

    tiledb_config = storage_options or dict()
    # encryption key, if any
    key = tiledb_config.pop('key', None)

    if not da.core._check_regular_chunks(darray.chunks):
        raise ValueError('Attempt to save array to TileDB with irregular '
                         'chunking, please call `arr.rechunk(...)` first.')

    if isinstance(uri, str):
        chunks = [c[0] for c in darray.chunks]
        key = kwargs.pop('key', None)
        # create a suitable, empty, writable TileDB array
        tdb = tiledb.empty_like(uri, darray, tile=chunks, config=tiledb_config, key=key)
    elif isinstance(uri, tiledb.Array):
        tdb = uri
        # sanity checks
        if not ((darray.shape == tdb.shape) and
                (darray.dtype == tdb.dtype) and
                (darray.ndim == tdb.ndim)):
            raise ValueError("Target TileDB array layout is not compatible with "
                             "source array")
    else:
        raise ValueError("'uri' must be string pointing to supported TileDB store location "
                         "or an open, writable TileDB array.")

    if not (tdb.isopen and tdb.iswritable):
        raise ValueError("Target TileDB array is not open and writable.")

    return darray.store(tdb, lock=False, compute=compute,
                        return_stored=return_stored)
