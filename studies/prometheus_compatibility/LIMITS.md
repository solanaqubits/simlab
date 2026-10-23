# Scope and non-composition limits

The 14 entries in `registry.json` are the canonical English claim inventory. Requirements that are false remain blocked; absent or null requirements remain unsupported. Numeric decimal strings preserve their reported values without binary floating-point conversion. Equal metadata only establishes equal selected labels/values.

Mandatory exclusions include:

- A flight time for a 12114.627 km chord cannot be transferred to a receiver modeled for 10800 km without a common geometry and detector calibration.
- The analytical repetition100 bound, at rate 1/100 under its stipulated channel law, does not certify the 256-bit RS(240,36), repetition5 and CRC32 implementation.
- Sparse 4-5 ms packet arrivals, decoder medians and queue tails are different from full-rate 96 microsecond arrivals and from a worst-case execution-time guarantee. No per-packet guarantee is inferred from a median or worker count.
- Delivered BER, erasures, sifted QBER and packet failure probabilities have different denominators and assumptions. Finite-sample Wilson intervals do not prove PER below 1e-9. A 95% two-sided Wilson zero-failure upper bound and a one-sided bound must not be conflated.
- NQKD had 5408 candidate Z bits after sifting and test disclosure; 3937 candidates remained after error correction, consistency checking and Toeplitz compression. This is not a certified positive secret-key rate. The 10% intercept-resend run failed its consistency check, not a formally certified security threshold. The f/4 formula applies only to the specified ideal attack model.
- CD2 neutron kinetic yield near 1.18 microjoules does not establish registration jitter, moderation/capture efficiency or biological viability under a 1500 W optical load. Optical pulse duration is not arrival-time precision.
- T-AKL phase invariance concerns amplitude norm and the specified rate with fixed density of states. A supplied phase-dependent density correction is conditional, not a first-principles beta-decay QFT derivation. Roughly 13.2 billion decays per group is an ideal Fisher/Gaussian estimate, not a detection guarantee. Storage losses and intrinsic beta decay require independent identification.

Additional editorial boundaries NC05, NC08, NC09, NC10, NC12 and NC14 remain explicit even where a related machine group exists. The group checker does not infer physical mechanisms, temporal mantle covariance, realized neutrino qubit encoding, general cryptographic secrecy, universal phase invariance or beta-lifetime identifiability.

No scientific experiment, physical simulation, new Lean proof, full-library rebuild, new axiom audit or thermal/security certification was performed for this publication. The frozen grant application and private evidence remain separate. Publication changes visibility of this selected package, not the evidence level of its claims.
