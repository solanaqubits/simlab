# Quantum circuit examples

Optional numerical request corpus for [SimLab Quantum](../../docs/quantum-simulator.en.md).
Derived from Quantum `f787b023e57cd4b011ccae73638706d441707400` examples.

Every case has explicit mode, seed 42 and 128 shots. Analytical checks use absolute
1e-12 tolerances on these small cases; wrapper acceptance invariants use 1e-9.
Bell and GHZ target endpoint superpositions, Grover targets |11>, QFT example has
support |100>,|101>, noise uses its specified density-matrix channel, and
teleportation preserves qubit 2's Bloch vector (sqrt(3)/2,0,1/2).
No model here asserts a physical device result or algorithmic speedup.
