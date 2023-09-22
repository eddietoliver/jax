# Copyright 2018 The JAX Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utilities for pseudo-random number generation.

The :mod:`jax.random` package provides a number of routines for deterministic
generation of sequences of pseudorandom numbers.

Basic usage
-----------

>>> seed = 1701
>>> num_steps = 100
>>> key = jax.random.key(seed)
>>> for i in range(num_steps):
...   key, subkey = jax.random.split(key)
...   params = compiled_update(subkey, params, next(batches))  # doctest: +SKIP

PRNG keys
---------

Unlike the *stateful* pseudorandom number generators (PRNGs) that users of NumPy and
SciPy may be accustomed to, JAX random functions all require an explicit PRNG state to
be passed as a first argument.
The random state is described by a special array element type that we call a **key**,
usually generated by the :py:func:`jax.random.key` function::

    >>> from jax import random
    >>> key = random.key(0)
    >>> key
    Array((), dtype=key<fry>) overlaying:
    [0 0]

This key can then be used in any of JAX's random number generation routines::

    >>> random.uniform(key)
    Array(0.41845703, dtype=float32)

Note that using a key does not modify it, so reusing the same key will lead to the same result::

    >>> random.uniform(key)
    Array(0.41845703, dtype=float32)

If you need a new random number, you can use :meth:`jax.random.split` to generate new subkeys::

    >>> key, subkey = random.split(key)
    >>> random.uniform(subkey)
    Array(0.10536897, dtype=float32)

.. note::

   Typed key arrays, with element types such as ``key<fry>`` above,
   were introduced in JAX v0.4.16. Before then, keys were
   conventionally represented in ``uint32`` arrays, whose final
   dimension represented the key's bit-level representation.

   Both forms of key array can still be created and used with the
   :mod:`jax.random` module. New-style typed key arrays are made with
   :py:func:`jax.random.key`. Legacy ``uint32`` key arrays are made
   with :py:func:`jax.random.PRNGKey`.

   To convert between the two, use :py:func:`jax.random.key_data` and
   :py:func:`jax.random.wrap_key_data`. The legacy key format may be
   needed when interfacing with systems outside of JAX (e.g. exporting
   arrays to a serializable format), or when passing keys to JAX-based
   libraries that assume the legacy format.

   Otherwise, typed keys are recommended. Caveats of legacy keys
   relative to typed ones include:

   * They have an extra trailing dimension.

   * They have a numeric dtype (``uint32``), allowing for operations
     that are typically not meant to be carried out over keys, such as
     integer arithmetic.

   * They do not carry information about the RNG implementation. When
     legacy keys are passed to :mod:`jax.random` functions, a global
     configuration setting determines the RNG implementation (see
     "Advanced RNG configuration" below).

   To learn more about this upgrade, and the design of key types, see
   `JEP 9263
   <https://jax.readthedocs.io/en/latest/jep/9263-typed-keys.html>`_.

Advanced
--------

Design and background
=====================

**TLDR**: JAX PRNG = `Threefry counter PRNG <http://www.thesalmons.org/john/random123/papers/random123sc11.pdf>`_
+ a functional array-oriented `splitting model <https://dl.acm.org/citation.cfm?id=2503784>`_

See `docs/jep/263-prng.md <https://github.com/google/jax/blob/main/docs/jep/263-prng.md>`_
for more details.

To summarize, among other requirements, the JAX PRNG aims to:

1.  ensure reproducibility,
2.  parallelize well, both in terms of vectorization (generating array values)
    and multi-replica, multi-core computation. In particular it should not use
    sequencing constraints between random function calls.

Advanced RNG configuration
==========================

JAX provides several PRNG implementations. A specific one can be
selected with the optional `impl` keyword argument to
`jax.random.key`. When no `impl` option is passed to the `key`
constructor, the implementation is determined by the global
`jax_default_prng_impl` configuration flag.

-   **default**, `"threefry2x32"`:
    `A counter-based PRNG built around the Threefry hash function <http://www.thesalmons.org/john/random123/papers/random123sc11.pdf>`_.
-   *experimental* A PRNG that thinly wraps the XLA Random Bit Generator (RBG) algorithm. See
    `TF doc <https://www.tensorflow.org/xla/operation_semantics#rngbitgenerator>`_.

    -   `"rbg"` uses ThreeFry for splitting, and XLA RBG for data generation.
    -   `"unsafe_rbg"` exists only for demonstration purposes, using RBG both for
        splitting (using an untested made up algorithm) and generating.

    The random streams generated by these experimental implementations haven't
    been subject to any empirical randomness testing (e.g. Big Crush). The
    random bits generated may change between JAX versions.

The possible reasons not use the default RNG are:

1.  it may be slow to compile (specifically for Google Cloud TPUs)
2.  it's slower to execute on TPUs
3.  it doesn't support efficient automatic sharding / partitioning

Here is a short summary:

.. table::
   :widths: auto

   =================================   ========  =========  ===  ==========  =====  ============
   Property                            Threefry  Threefry*  rbg  unsafe_rbg  rbg**  unsafe_rbg**
   =================================   ========  =========  ===  ==========  =====  ============
   Fastest on TPU                                           ✅   ✅          ✅     ✅
   efficiently shardable (w/ pjit)                ✅                         ✅     ✅
   identical across shardings           ✅        ✅        ✅   ✅
   identical across CPU/GPU/TPU         ✅        ✅
   identical across JAX/XLA versions    ✅        ✅
   =================================   ========  =========  ===  ==========  =====  ============

(*): with jax_threefry_partitionable=1 set
(**): with XLA_FLAGS=--xla_tpu_spmd_rng_bit_generator_unsafe=1 set

The difference between "rbg" and "unsafe_rbg" is that while "rbg" uses a less
robust/studied hash function for random value generation (but not for
`jax.random.split` or `jax.random.fold_in`), "unsafe_rbg" additionally uses less
robust hash functions for `jax.random.split` and `jax.random.fold_in`. Therefore
less safe in the sense that the quality of random streams it generates from
different keys is less well understood.

For more about `jax_threefry_partitionable`, see
https://jax.readthedocs.io/en/latest/notebooks/Distributed_arrays_and_automatic_parallelization.html#generating-random-numbers
"""

# Note: import <name> as <name> is required for names to be exported.
# See PEP 484 & https://github.com/google/jax/issues/7570

from jax._src.random import (
  PRNGKey as PRNGKey,
  ball as ball,
  bernoulli as bernoulli,
  binomial as binomial,
  beta as beta,
  bits as bits,
  categorical as categorical,
  cauchy as cauchy,
  chisquare as chisquare,
  choice as choice,
  dirichlet as dirichlet,
  double_sided_maxwell as double_sided_maxwell,
  exponential as exponential,
  f as f,
  fold_in as fold_in,
  gamma as gamma,
  generalized_normal as generalized_normal,
  geometric as geometric,
  gumbel as gumbel,
  key as key,
  key_data as key_data,
  key_impl as key_impl,
  laplace as laplace,
  logistic as logistic,
  loggamma as loggamma,
  lognormal as lognormal,
  maxwell as maxwell,
  multivariate_normal as multivariate_normal,
  normal as normal,
  orthogonal as orthogonal,
  pareto as pareto,
  permutation as permutation,
  poisson as poisson,
  rademacher as rademacher,
  randint as randint,
  random_gamma_p as random_gamma_p,
  rayleigh as rayleigh,
  shuffle as _deprecated_shuffle,
  split as split,
  t as t,
  triangular as triangular,
  truncated_normal as truncated_normal,
  uniform as uniform,
  wald as wald,
  weibull_min as weibull_min,
  wrap_key_data as wrap_key_data,
)

_deprecations = {
    # Added November 6, 2023; but has been raising a FutureWarning since JAX 0.1.66
    "shuffle": (
        "jax.random.shuffle is deprecated. Use jax.random.permutation with independent=True.",
        _deprecated_shuffle,
    )
}

import typing
if typing.TYPE_CHECKING:
  shuffle = _deprecated_shuffle
else:
  from jax._src.deprecations import deprecation_getattr as _deprecation_getattr
  __getattr__ = _deprecation_getattr(__name__, _deprecations)
  del _deprecation_getattr
del typing
