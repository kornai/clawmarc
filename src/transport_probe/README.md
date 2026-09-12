# Clawmarc transport probe

This probe tests whether a set of CXCC cards can be transported to another
machine without changing their verification or ranking behaviour. It uses
only Python and `cryptography`; it does not load an embedding model.

## Install and test

```sh
make install PREFIX="$HOME/.local"
make test
```

If `make install` reports that `cryptography` is missing, install it in the
Python environment selected by `PYTHON`, then repeat the command.

## Reference run on the M1

Put the cards to be transported in one directory and select one card with an
embedding as the query. The query card need not be in the corpus.

```sh
python3 probe.py --cards ./cards --query ./query.cxcc \
  --write-reference transport_reference.json
```

The reference JSON records the verified card identifiers, embedding profiles,
and top-k order. Transfer this directory, the cards, the query card, and the
reference JSON to Linux. On Linux run:

```sh
python3 probe.py --cards ./cards --query ./query.cxcc \
  --expected transport_reference.json --output transport_linux.json
```

Exit status zero means that every card and the query passed size, CRC,
signature, and embedding-digest checks, and that the ranking order matched the
M1 reference. A nonzero status identifies the first mismatch. The ranking is
computed with little-endian IEEE binary16 values and deterministic
tie-breaking by card identifier.

The primary transportability result is the verification and ranking match.
It does not claim that re-running neural inference on two operating systems
will produce identical vectors; that is a separate runtime-drift experiment.

## Making the transfer archive

After producing `transport_reference.json`, transfer the complete probe source,
the cards directory, the query card, and the reference JSON. For example:

```sh
tar -czf clawmarc-transport-probe.tgz transport_probe cards query.cxcc transport_reference.json
```

On Linux, unpack it, install `cryptography` if necessary, run `make install`
and `make test` in `transport_probe`, then run the comparison command above.
